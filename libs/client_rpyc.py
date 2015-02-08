import os
import time
import logging
from threading import Thread
from plumbum import SshMachine
from libs.config_parser import get_config_data
from rpyc.utils.zerodeploy import DeployedServer

class big_bang:

    def __init__(self):
        """
            Initialises the whole environment and establishes connection
        """
        self.config_data = get_config_data()

        self.nodes = self.config_data['NODES']
        self.peers = self.config_data['PEERS']
        self.clients = self.config_data['CLIENTS']
        self.gm_nodes = self.config_data['GM_NODES']
        self.gm_peers = self.config_data['GM_PEERS']
        self.gs_nodes = self.config_data['GS_NODES']
        self.gs_peers = self.config_data['GS_PEERS']
        self.number_nodes = len(self.nodes)
        self.number_peers = len(self.peers)
        self.number_clients = len(self.clients)
        self.number_gm_nodes = len(self.gm_nodes)
        self.number_gm_peers = len(self.gm_peers)
        self.number_gs_nodes = len(self.gs_nodes)
        self.number_gs_peers = len(self.gs_peers)

        self.servers = self.nodes + self.peers + self.gm_nodes + self.gm_peers \
                       + self.gs_nodes + self.gs_peers
        self.all_nodes = self.nodes + self.peers + self.clients + self.gm_nodes\
                         + self.gm_peers + self.gs_nodes + self.gs_peers

        client_logfile = self.config_data['LOG_FILE']
        loglevel = getattr(logging, self.config_data['LOG_LEVEL'].upper())
        client_logdir = os.path.dirname(client_logfile)
        if not os.path.exists(client_logdir):
            os.makedirs(client_logdir)
        self.logger = logging.getLogger('client_rpyc')
        self.lhndlr = logging.FileHandler(client_logfile)
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(funcName)s %(message)s')
        self.lhndlr.setFormatter(formatter)
        self.logger.addHandler(self.lhndlr)
        self.logger.setLevel(loglevel)

        self.user = self.config_data['REMOTE_USER']

        self.connection_handles = {}
        self.subp_conn = {}
        processes = []
        for node in self.all_nodes:
            self.connection_handles[node] = {}
            self.subp_conn[node] = {}
            p = Thread(target=self.establish_connection, args=(node, self.user))
            p.start()
            processes.append(p)
        for p in processes:
            p.join()

    def establish_connection(self, node, user):
        """
            Establishes connection from localhost to node via SshMachine and
            zerodeploy. The connection is authenticated and hence secure.
            Populates the connection in a dict called connection_handles.
            This function does not take care of timeouts. Timeouts need to
            be handled by the calling function
            Returns None
        """
        self.logger.debug("Connecting to node: %s" % node)
        rem = SshMachine(node, user)
        dep = DeployedServer(rem)
        conn = dep.classic_connect()
        self.connection_handles[node][user] = (rem, dep, conn)
        self.subp_conn[node][user] = conn.modules.subprocess
        return None

    def refresh_connection(self, node, user='', timeout=210):
        if user == '':
            user = self.user
        try:
            self.connection_handles[node][user][2].close()
            self.connection_handles[node][user][1].close()
            self.connection_handles[node][user][0].close()
        except:
            pass
        while timeout >= 0:
            try:
                self.establish_connection(node, user)
                break
            except:
                self.logger.debug("Couldn't connect to %s. Retrying in 42 secs" \
                % node)
                time.sleep(42)
                timeout = timeout - 42
        if timeout < 0:
            self.logger.critical("Unable to connect to %s" % node)
            return False
        else:
            self.logger.debug("Connection re-established to %s" % node)
            return True

    def run(self, node, cmd, user='', verbose=True):
        """
            Run the specified command in specified remote machine

            Returns a tuple of (retcode, stdout, stderr) of the command
            in remote machine
        """
        if user == '':
            user = self.user
        self.logger.info("Executing %s on %s" % (cmd, node))
        subp = self.subp_conn[node][user]
        try:
            p = subp.Popen(cmd, shell=True, stdout=subp.PIPE, stderr=subp.PIPE)
        except:
            ret = self.refresh_connection(node, user)
            if not ret:
                self.logger.critical("Connection to %s couldn't be established"\
                % node)
                return (-1, -1, -1)
            subp = self.subp_conn[node][user]
            p = subp.Popen(cmd, shell=True, stdout=subp.PIPE, stderr=subp.PIPE)
        pout, perr = p.communicate()
        ret = p.returncode
        self.logger.info("\"%s\" on %s: RETCODE is %d" % (cmd, node, ret))
        if pout != "" and verbose:
            self.logger.info("\"%s\" on %s: STDOUT is \n %s" % \
                            (cmd, node, pout))
        if perr != "" and verbose:
            self.logger.error("\"%s\" on %s: STDERR is \n %s" % \
                            (cmd, node, perr))
        return ( ret, pout, perr )

    def run_async(self, node, cmd, user='', verbose=True):
        """
            Run the specified command in specified remote node asynchronously
        """
        if user == '':
            user = self.user
        try:
            c = self.connection_handles[node][user][1].classic_connect()
        except:
            ret = self.refresh_connection(node, user)
            if not ret:
                self.logger.critical("Couldn't connect to %s" % node)
                return None
            c = self.connection_handles[node][user][1].classic_connect()
        self.logger.info("Executing %s on %s asynchronously" % (cmd, node))
        p = c.modules.subprocess.Popen(cmd, shell=True, \
            stdout=c.modules.subprocess.PIPE, stderr=c.modules.subprocess.PIPE)
        def value():
            pout, perr = p.communicate()
            retc = p.returncode
            c.close()
            self.logger.info("\"%s\" on \"%s\": RETCODE is %d" % \
            (cmd, node, retc))
            if pout != "" and verbose:
                self.logger.debug("\"%s\" on \"%s\": STDOUT is \n %s" % \
                (cmd, node, pout))
            if perr != "" and verbose:
                self.logger.error("\"%s\" on \"%s\": STDERR is \n %s" % \
                (cmd, node, perr))
            return (retc, pout, perr)
        p.value = value
        p.close = lambda: c.close()
        return p

    def run_servers(self, command, user='', verbose=True):
        """
            Run the specified command in each of the server in parallel
        """
        if user == '':
            user = self.user
        sdict = {}
        out_dict = {}
        ret = True
        for server in self.servers:
            sdict[server] = self.run_async(server, command, user, verbose)
        for server in self.servers:
            sdict[server].wait()
            ps, pout, perr = sdict[server].value()
            out_dict[server] = ps
            if 0 != ps:
                ret = False
        return (ret, out_dict)

    def get_connection(self, node, user=''):
        """
            Establishes a connection to the remote node and returns
            the connection handle. Returns -1 if connection couldn't
            be established.
        """
        if user == '':
            user = self.user
        try:
            conn = self.connection_handles[node][user][1].classic_connect()
        except:
            ret = self.refresh_connection(node, user)
            if not ret:
                self.logger.critical("Couldn't connect to %s" % node)
                return -1
        return conn

    def upload(self, node, localpath, remotepath, user=''):
        """
            Uploads the file/directory in localpath to file/directory to
            remotepath in node
            Returns None if success
            Raises an exception in case of failure
        """
        if user == '':
            user = self.user
        rem = self.connection_handles[node][user][0]
        rem.upload(localpath, remotepath)
        return None

    def fini(self):
        for node in self.connection_handles.keys():
            for user in node.keys():
                self.logger.debug("Closing all connection to %s@%s" \
                        % (user, node))
                self.connection_handles[node][user][2].close()
                self.connection_handles[node][user][1].close()
                self.connection_handles[node][user][0].close()
