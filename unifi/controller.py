try:
    # Ugly hack to force SSLv3 and avoid
    # urllib2.URLError: <urlopen error [Errno 1] _ssl.c:504: error:14077438:SSL routines:SSL23_GET_SERVER_HELLO:tlsv1 alert internal error>
    import _ssl
    _ssl.PROTOCOL_SSLv23 = _ssl.PROTOCOL_SSLv3
except:
    pass

import cookielib
import json
import logging
import urllib
import urllib2

log = logging.getLogger(__name__)

class APIError(Exception):
    pass

class Controller:
    """Interact with a UniFi controller.

    Uses the JSON interface on port 8443 (HTTPS) to communicate with a UniFi
    controller. Operations will raise unifi.controller.APIError on obvious
    problems (such as login failure), but many errors (such as disconnecting a
    nonexistant client) will go unreported.

    >>> from unifi.controller import Controller
    >>> c = Controller('192.168.1.99', 'admin', 'p4ssw0rd'
    >>> for ap in c.get_aps():
    ...     print 'AP named %s with MAC %s' % (ap['name'], ap['mac'])
    ...
    AP named Study with MAC dc:9f:db:1a:59:07
    AP named Living Room with MAC dc:9f:db:1a:59:08
    AP named Garage with MAC dc:9f:db:1a:59:0b

    """

    def __init__(self, host, username, password):
        """Create a Controller object.

        Arguments:
            host     -- the address of the controller host; IP or name
            username -- the username to log in with
            password -- the password to log in with

        """

        self.host = host
        self.username = username
        self.password = password
        self.url = 'https://' + host + ':8443/'
        log.debug('Controller for %s', self.url)

        cj = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))

        self._login()

    def _jsondec(self, data):
        obj = json.loads(data)
        if 'meta' in obj:
            if obj['meta']['rc'] != 'ok':
                raise APIError(obj['meta']['msg'])
        if 'data' in obj:
            return obj['data']
        return obj

    def _read(self, url, params=None):
        res = self.opener.open(url, params)
        return self._jsondec(res.read())

    def _login(self):
        log.debug('login() as %s', self.username)
        params = urllib.urlencode({'login': 'login',
            'username': self.username, 'password': self.password})
        self.opener.open(self.url + 'login', params).read()

    def get_aps(self):
        """Return a list of all AP:s, with significant information about each."""

        js = json.dumps({'_depth': 2, 'test': None})
        params = urllib.urlencode({'json': js})
        return self._read(self.url + 'api/stat/device', params)

    def get_clients(self):
        """Return a list of all active clients, with significant information about each."""

        return self._read(self.url + 'api/stat/sta')
    
    def get_quota(self,mac):
	client = [x for x in self.get_clients() if x.mac == mac]
	if len(client) > 0:
	  return max(int(client[0][rx_bytes]),int(client[0][tx_bytes]))
	else:
	  return 0
	
    def get_wlan_conf(self):
        """Return a list of configured WLANs with their configuration parameters."""

        return self._read(self.url + 'api/list/wlanconf')

    def run(self,command,mgr='api/cmd/stamgr',payload={}):
        log.debug('_run(%s, %s)', command,mgr)
        payload.update({'cmd':command})
        params = urllib.urlencode({'json': payload})
        self._read(self.url + mgr, params)
        
    def _mac_cmd(self, target_mac, command, mgr='stamgr'):
        log.debug('_mac_cmd(%s, %s)', target_mac, command)
        params = urllib.urlencode({'json':
            {'mac': target_mac, 'cmd': command}})
        self._read(self.url + 'api/cmd/' + mgr, params)

    #authorize parameters {minutes,up,down,bytes}
    def _mac_extcmd(self, target_mac, command, mgr='stamgr',payload={}):
        log.debug('_mac_extcmd(%s, %s)', target_mac, command)
        payload.update({'mac': target_mac, 'cmd': command})
        params = urllib.urlencode({'json':payload})
        self._read(self.url + 'api/cmd/' + mgr, params)
        

    def authorize(self,mac,minutes=800,payload={}):
	payload.update({'minutes':minutes})
	self._mac_extcmd(mac,'authorize-guest',payload)
	
    def unauthorize(self,mac):
	self._mac_cmd(mac,'unauthorize-guest')
      
    def block_client(self, mac):
        """Add a client to the block list.

        Arguments:
            mac -- the MAC address of the client to block.

        """

        self._mac_cmd(mac, 'block-sta')

    def unblock_client(self, mac):
        """Remove a client from the block list.

        Arguments:
            mac -- the MAC address of the client to unblock.

        """

        self._mac_cmd(mac, 'unblock-sta')

    def disconnect_client(self, mac):
        """Disconnect a client.

        Disconnects a client, forcing them to reassociate. Useful when the
        connection is of bad quality to force a rescan.

        Arguments:
            mac -- the MAC address of the client to disconnect.

        """

        self._mac_cmd(mac, 'kick-sta')

    def restart_ap(self, mac):
        """Restart an access point (by MAC).

        Arguments:
            mac -- the MAC address of the AP to restart.

        """

        self._mac_cmd(mac, 'restart', 'devmgr')

    def restart_ap_name(self, name):
        """Restart an access point (by name).

        Arguments:
            name -- the name address of the AP to restart.

        """

        if not name:
            raise APIError('%s is not a valid name' % str(name))
        for ap in self.get_aps():
            if ap.get('state', 0) == 1 and ap.get('name', None) == name:
                self.reboot_ap(ap['mac'])

