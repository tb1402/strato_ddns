# import httplib
# import daemon
from encodings import utf_8
import ipaddress
import argparse
from unittest import result
import dns.resolver as resolver
import dns
import urllib.request
import time
import base64
from netifaces import AF_INET6, ifaddresses


class strato_ddns:

    def __init__(self, config_path="./ddns.conf", debug=False, dryrun=False):

        self.debug = debug
        self.dry = dryrun
        # init variables
        self.daemon = 3600
        self.server = "dyndns.strato.com"
        self.query_url = "/nic/update?"
        self.login = ""
        self.password = ""
        self.domain = []
        self.ipv4 = ""  # web?

        self.ipv4_dns = ""
        self.ipv4_real = ""
        self.ipv6 = ""  # web?
        self.ipv6_dns = ""
        self.ipv6_real = ""
        self.ipv6_suffix = ""
        self.ipv6_netmask = 64
        self.nameservers = ['8.8.8.8', '8.8.4.4', '2001:4860:4860::8888', '2001:4860:4860::8844']

        self.ipv4_check_url = 'http://ipv4.ident.me'
        self.ipv6_check_url = 'http://ipv6.ident.me'

        # read config
        self.read_config(config_path=config_path)

        if self.login == "" or self.password == "" or self.domain == []:
            raise Exception("Missing information (login/pwd/domain) in .conf")
        if self.ipv4 == "" or self.ipv6 == "":
            raise Exception("Missing information (IPv4/IPv6) in .conf")
        # if ipv6 is web but no suffix given
        if self.ipv6 == "web" and self.ipv6_suffix == "":
            raise Exception("Missing IPv6 suffix, please lookup in your router!")

        # prepare resolver
        self.resolver = resolver.Resolver()
        self.resolver.nameservers = self.nameservers

        # prepare urllib
        # create a password manager
        self.password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()

        # Add the username and password.
        # If we knew the realm, we could use it instead of None.
        top_level_url = "https://" + self.server
        self.password_mgr.add_password(None, top_level_url, self.login, self.password)

        self.handler = urllib.request.HTTPBasicAuthHandler(self.password_mgr)

        # create "opener" (OpenerDirector instance)
        self.opener = urllib.request.build_opener(self.handler)

    def read_config(self, config_path):
        if self.debug: print("reading and processing debug file")

        f = open(config_path)
        try:
            lines = f.readlines()
            for l in lines:
                l = l.strip()
                if l.startswith('#'):
                    # exclude comments
                    pass
                elif l == "":
                    # pass empty lines
                    pass
                else:
                    c = l.split('=')
                    option = str(c[0]).strip()
                    value = str(c[1]).strip()

                    if self.debug: print("option:", option, "\tvalue:", value)

                    if option == "daemon":
                        self.daemon = int(value)
                    elif option == "server":
                        self.server = str(value).strip()
                    elif option == "query_url":
                        self.query_url = str(value).strip()
                    elif option == "login":
                        self.login = str(value).strip()
                    elif option == "password":
                        self.password = str(value).strip()
                    elif option == "domain":
                        self.domain = str(value).strip().split(',')
                    elif option == "nameserver":
                        self.nameservers = str(value).strip().split(',')
                        # check each number fot ip-validation
                        for n in self.nameservers:
                            ip = ipaddress.ip_address(n)
                    elif option == "ipv4":
                        value = str(value).strip()
                        if value == "web":
                            self.ipv4 = value
                        else:
                            # parses to ip, throws error if no ip given
                            ip = ipaddress.IPv4Address(value)
                            self.ipv4 = value
                    elif option == "ipv6":
                        value = str(value).strip()
                        if value == "web":
                            self.ipv6 = value
                        elif value.startswith("interface"):
                            interface_name = value.replace("interface:", "")

                            # get v6 addresses for interface
                            for address in ifaddresses(interface_name)[AF_INET6]:
                                # very basic check to skip link local or unique local addresses
                                if address["addr"].startswith("f"):
                                    continue

                                self.ipv6 = address["addr"]
                                break
                        else:
                            # parses to ip, throws error if no ip given
                            ip = ipaddress.IPv6Address(value)
                            self.ipv6 = value
                    elif option == "ipv6_suffix":
                        ip = ipaddress.IPv6Address(value)
                        print(str(ip.exploded))
                        self.ipv6_suffix = value
                    elif option == "ipv6_netmask":
                        value = int(value)
                        if value < 0 or value > 128:
                            raise ValueError("Netmask out of valid values")
                        self.ipv6_netmask = value
                    elif option == "ipv6_url":
                        self.ipv6_check_url = value
                    elif option == "ipv4_url":
                        self.ipv4_check_url = value
                    else:
                        # unexpected arguments in configuration
                        raise Exception("invalid configuration")

        except Exception as e:
            print("Could not process .conf: ", str(e))
            exit()

        finally:
            f.close()
            if self.debug: print("FINISHED .config\n")

    def run(self):

        for d in self.domain:
            # form updatestring
            if self.debug: print("\nSTART: update run for", d)
            # prepare IPv4
            if self.ipv4 != "":

                # Lookup current dns ipv4
                try:
                    self.ipv4_dns = self.resolver.resolve(d, rdtype=dns.rdatatype.A)  # (d, 'A')

                except:
                    if self.debug:
                        print("Could not look up IPv4 address...")
                if len(self.ipv4_dns) <= 0:
                    self.ipv4_dns = 'none'
                # elif len(self.ipv4_dns) >= 1: self.ipv4_dns = self.ipv4_dns[0]
                else:
                    self.ipv4_dns = str(self.ipv4_dns[0])
                if self.debug: print("Resolved domain", d, "to IPv4\t", self.ipv4_dns)

                # if ipv4==web -> lookup real ip, else use static
                if self.ipv4 == "web":
                    try:
                        self.ipv4_real = urllib.request.urlopen(self.ipv4_check_url).read().decode('utf8')
                    except:
                        if self.debug:
                            print("Could not get real IPv6 address, using looked up IPv6...")
                    if self.debug: print("Real external IPv4 is\t\t\t", self.ipv4_real)
                else:
                    self.ipv4_real = self.ipv4
                    if self.debug: print("Static external IPv4 is", self.ipv4_real)

            # prepare IPv6
            if self.ipv6 != "":

                # Lookup ipv6 on DNS
                try:
                    self.ipv6_dns = self.resolver.resolve(d, rdtype=dns.rdatatype.AAAA)  # (d, 'AAAA')
                except:
                    if self.debug:
                        print("Could not look up IPv6 address...")
                if len(self.ipv6_dns) <= 0:
                    self.ipv6_dns = 'none'
                # elif len(self.ipv6_dns) >= 1: self.ipv6_dns = self.ipv6_dns[0]
                else:
                    self.ipv6_dns = str(self.ipv6_dns[0])
                if self.debug: print("Resolved domain", d, "to IPv6\t", self.ipv6_dns)
                if self.ipv6 == "web":
                    try:
                        self.ipv6_real = urllib.request.urlopen(self.ipv6_check_url).read().decode('utf8')
                    except:
                        if self.debug:
                            print("Could not get real IPv6 address, using looked up IPv6...")

                    # IP address from which we take the network part ("prefix")
                    if self.debug:
                        print(f"REAL IPv6 ist {self.ipv6_real}")
                    net_addr = ipaddress.IPv6Address(self.ipv6_real)
                    # IP address from which we take the host part (suffix)
                    host_addr = ipaddress.IPv6Address(self.ipv6_suffix)
                    self.ipv6_real = str(self.replace_ipv6_host_part(net_addr, host_addr))
                    if self.debug: print("Real external IPv6 is\t\t\t", self.ipv6_real)
                else:
                    self.ipv6_real = self.ipv6
                    if self.debug: print("Static external IPv6 is\t\t\t", self.ipv6_real)

            # if change is True, a update is necessary
            if self.ipv4_dns != self.ipv4_real or self.ipv6_dns != self.ipv6_real:
                if self.debug: print("\nUPDATE NECESSARY")
                update_string = "https://" + self.server + self.query_url
                update_string = update_string + "hostname=" + d + "&"
                update_string = update_string + "myip="
                if self.ipv4 != "":
                    update_string = update_string + self.ipv4_real
                if self.ipv4 != "" and self.ipv6 != "":
                    update_string = update_string + ","
                if self.ipv6 != "":
                    update_string = update_string + self.ipv6_real

                if self.debug: print("\nUPDATESTRING:", update_string)

                # use the opener to fetch a URL
                self.opener.open(update_string)

                # Install the opener.
                # Now all calls to urllib.request.urlopen use our opener.
                urllib.request.install_opener(self.opener)

                if not self.dry:
                    update_response = urllib.request.urlopen(update_string)
                    code = update_response.code
                    if str(code) != "200":
                        print("Error-Code:", code)

                    update_response = update_response.read().decode('utf_8')
                    if update_response.startswith("abuse"):
                        print("ABUSE:", update_response)
                    else:
                        print("whatever:", update_response)
                # TODO: log response
            else:
                if self.debug: print("All up to date!")

    # ipv6 combination from https://techoverflow.net/2021/12/10/how-to-replace-host-part-of-ipv6-address-using-python/
    def bitwise_and_ipv6(self, addr1, addr2):
        result_int = int.from_bytes(addr1.packed, byteorder="big") & int.from_bytes(addr2.packed, byteorder="big")
        return ipaddress.IPv6Address(result_int.to_bytes(16, byteorder="big"))

    def bitwise_or_ipv6(self, addr1, addr2):
        result_int = int.from_bytes(addr1.packed, byteorder="big") | int.from_bytes(addr2.packed, byteorder="big")
        return ipaddress.IPv6Address(result_int.to_bytes(16, byteorder="big"))

    def bitwise_xor_ipv6(self, addr1, addr2):
        result_int = int.from_bytes(addr1.packed, byteorder="big") ^ int.from_bytes(addr2.packed, byteorder="big")
        return ipaddress.IPv6Address(result_int.to_bytes(16, byteorder="big"))

    def replace_ipv6_host_part(self, net_addr, host_addr):
        netmask_length = self.ipv6_netmask
        # Compute bitmasks
        prefix_network = ipaddress.IPv6Network(f"::/{netmask_length}")
        hostmask = prefix_network.hostmask  # ffff:ffff:ffff:ffff:: for /64
        netmask = prefix_network.netmask  # ::ffff:ffff:ffff:ffff for /64
        # Compute address
        net_part = self.bitwise_and_ipv6(net_addr, netmask)
        host_part = self.bitwise_and_ipv6(host_addr, hostmask)
        # Put together resulting IP
        return self.bitwise_or_ipv6(net_part, host_part)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Updates ip on strato dyndns")
    parser.add_argument(
        '--config',
        '-c',
        help="configuration file",
        type=str,
        default="./strato_ddns.conf",
        required=False
    )
    parser.add_argument(
        '--debug',
        '-d',
        help="turn on debug information",
        action="store_true"
    )
    parser.add_argument(
        '--dryrun',
        '-t',
        help='run dry, do not actualy set anything new',
        action='store_true'
    )

    parser.add_argument(
        '--interval',
        '-i',
        help="interval to check an update in seconds",
        type=int,
        default=600
    )

    args = parser.parse_args()

    debug = False
    if args.debug: debug = True

    s = strato_ddns(config_path=args.config, debug=debug, dryrun=args.dryrun)
    # while True:
    s.run()
    # time.sleep(args.interval)
