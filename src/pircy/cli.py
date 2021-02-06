
import asyncio, hashlib, logging, os, pwd, socket
from concurrent.futures import ThreadPoolExecutor

import click
import hcl

import pircy.main as main
from .pluginbase import PluginBase, PluginSource
from .util import gen_password

try:
    import uvloop
except ImportError:
    uvloop = None


ScriptContext = main.ScriptContext

class color:
    purple = '\033[95m'
    blue = '\033[94m'
    green = '\033[92m'
    orange = '\033[93m'
    red = '\033[91m'
    end = '\033[0m'
    def disable(self):
        self.purple = ''
        self.blue = ''
        self.green = ''
        self.orange = ''
        self.red = ''
        self.end = ''


def apply_config(config):
    """
    `apply_config` maps blocks of HCL to globals that are used throughout
    the IRCD.
    """
    # NOTE: The logging module is available globally if you'd
    #       like to define formatting in the configuration file.
    # There's also nothing stopping you from applying multiple configs.
    if "oper" in config:
        oper_block = config["oper"]
        # NOTE(ljb): Should be a list of username / password_hash tuples.
        if "username" in oper_block:
            if oper_block["username"] == True:
                main.OPER_USERNAME = os.getenv("USER")
            else:
                main.OPER_USERNAME = oper_block["username"]

        if "password" in oper_block:
            main.OPER_PASSWORD = oper_block["password"]

    if not "server" in config:
        raise ConfigurationError("\"server\" block missing from Psyrcd configuration.")

    server_block = config["server"]

    if isinstance(server_block, dict):
        config["server"] = ScriptContext(**server_block)

    if "name" in server_block:
        global SRV_NAME
        SRV_NAME = server_block["name"]
    if "domain" in server_block:
        main.SRV_DOMAIN = server_block["domain"]
    if "description" in server_block:
        main.SRV_DESCRIPTION = server_block["description"]
    if "welcome" in server_block:
        main.SRV_WELCOME = server_block["welcome"].format(SRV_NAME)

    if "ping_frequency" in server_block:
        global PING_FREQUENCY
        PING_FREQUENCY = server_block["ping_frequency"]

    if not "max" in config["server"]:
        raise ConfigurationError("\"max\" block missing from \"server\" block in Psyrcd configuration.")

    max_block = server_block["max"]

    if isinstance(server_block["max"], dict):
        config["server"]["max"] = ScriptContext(**max_block)

    if "channels" in max_block:
        global MAX_CHANNELS
        MAX_CHANNELS = max_block["channels"]
    if "clients" in max_block:
        global MAX_CLIENTS
        MAX_CLIENTS = max_block["clients"]
    if "idle_time" in max_block:
        global MAX_IDLE
        MAX_IDLE = max_block["idle_time"]
    if "nicklen" in max_block:
        global MAX_NICKLEN
        MAX_NICKLEN = max_block["nicklen"]
    if "topiclen" in max_block:
        global MAX_TOPICLEN
        MAX_TOPICLEN = max_block["topiclen"]

    # Return an object with simple attribute lookup semantics
    #
    # Permits things like `self.server.config.server.max.clients` from
    # instances of `IRCClient`.
    #
    # Only caveat is the special handling of keys named "line" as we're reusing
    # `ScriptContext`.
    #
    return ScriptContext(**config)


@click.group()
def cli():
    pass


@cli.command(help='version')
def version():
    from . import version
    click.echo("pircy {}".format(version))


@cli.command(help='run')
@click.option('-c', '--config', default='pircy.conf', help='config file')
@click.option('-l', '--logfile', default='stdout',
    help='log file or leave absent for stdout')
@click.option('-p', '--pidfile', default=False, help='pidfile path')
@click.option('-d', '--debug', default=False, help='debug')
@click.option('-f', '--foreground', is_flag=True, default=False,
    help='run in foreground')
def run(config, logfile, pidfile, debug, foreground):
    prog = "pircy"
    description = "The %spIRCy%s Server." % (color.orange,color.end)
    epilog = "Using the %s-k%s and %s-c%s options together enables SSL and plaintext connections over the same port." % \
        (color.blue,color.end,color.blue,color.end)

    # Read and apply the configuration file.
    with open(config, "r") as fd:
        config = hcl.load(fd)

    config = apply_config(config)

    if logfile == 'stdout':
        log = logging.basicConfig(
            level=logging.DEBUG if debug else logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s')
    else:
        log = logging.basicConfig(
            level=logging.DEBUG if debug else logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            filename=logfile,
            filemode='a')
        logging.info("Logging to %s" % (logfile))

    if debug:
        console = logging.StreamHandler()
        formatter = logging.Formatter('[%(levelname)s] %(message)s')
        console.setFormatter(formatter)
        console.setLevel(logging.DEBUG)
        logging.getLogger('').addHandler(console)

    if (pwd.getpwuid(os.getuid())[2] == 0):
        logging.info("Running as root is not permitted.")
        raise SystemExit

    if main.OPER_PASSWORD == True:
        main.OPER_PASSWORD = gen_password()
    print("Netadmin login: {}/oper {} {}{}".format(
        color.green, main.OPER_USERNAME, main.OPER_PASSWORD, color.end) )
    # Detach from console, reparent to init
    if not foreground:
        pidfile = pidfile or config['runtime']['pidfile']
        main.Daemon(pidfile)

    # Hash the password in memory.
    main.OPER_PASSWORD = hashlib.sha512(
        main.OPER_PASSWORD.encode('utf-8')).hexdigest()

    if config['runtime']['ssl_cert'] and config['runtime']['ssl_key']:
        logging.info("SSL Enabled.")

    # Set variables for processing script files:
    scripts_dir = config['runtime']['script_dir']
    if scripts_dir:
        this_dir = os.path.abspath(os.path.curdir) + os.path.sep
        scripts_dir = this_dir + scripts_dir + os.path.sep
        if os.path.isdir(scripts_dir):
            logging.info("Scripts directory: %s" % scripts_dir)
        else:
            scripts_dir = False

    # Ready a server instance.
    if uvloop != None:
        asyncio.set_event_loop(uvloop.new_event_loop())

    ThreadPool = ThreadPoolExecutor(MAX_CLIENTS)
    EventLoop  = asyncio.get_event_loop()
    ircserver  = main.IRCServer(
                    EventLoop,
                    config,
                    (config['runtime']['listen_address'],
                        int(config['runtime']['listen_port']) ),
                    config['runtime']['plugin_paths'],
                    read_on_exec=debug,
                    )
    # Start.
    try:
        if config['runtime']['plugin_paths']:
            ircserver.plugins.init(config)

        if scripts_dir:
            for filename in os.listdir(scripts_dir):
                if os.path.isfile(scripts_dir + filename):
                    ircserver.scripts.load(filename)

        ircserver.loop.call_later(PING_FREQUENCY, main.ping_routine, EventLoop)
        logging.info('Starting pircy on {}:{}'.format(
            config['runtime']['listen_address'],
            config['runtime']['listen_port'] ))
        ircserver.loop.set_debug(debug)
        ircserver.loop.run_forever()
    except socket.error as e:
        logging.error(repr(e))
        sys.exit(-2)
    except KeyboardInterrupt:
        ircserver.loop.stop()
        ThreadPool.shutdown()
        if scripts_dir:
            scripts = []
            for x in ircserver.scripts.i.values():
                for script in x.values():
                    scripts.append(script[0].file)
            scripts = set(scripts)
            for script in scripts:
                ircserver.scripts.unload(script[script.rfind(os.sep)+1:])
        logging.info('Bye.')
        raise SystemExit



if __name__ == '__main__':
    cli()
