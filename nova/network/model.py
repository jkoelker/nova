# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import json
import netaddr
import types


class Model(dict):
    def __repr__(self):
        return self.__class__.__name__ + '(' + dict.__repr__(self) + ')'


class IP(Model):
    def __init__(self, address=None, type=None, **kwargs):
        super(IP, self).__init__()

        self['address'] = address
        self['type'] = type
        self['version'] = kwargs.get('version')

        # determine version from address if not passed in
        if self['address'] and not self['version']:
            self['version'] = netaddr.IPAddress(self['address']).version

    def __eq__(self, other):
        return self['address'] == other['address']

    @classmethod
    def hydrate(cls, ip):
        if ip:
            ip = IP(**ip)
        return ip


class FixedIP(IP):
    def __init__(self, floating_ips=None, **kwargs):
        super(FixedIP, self).__init__(**kwargs)

        self['floating_ips'] = floating_ips or []
        if not self['type']:
            self['type'] = 'fixed'

    def add_floating_ip(self, floating_ip):
        if floating_ip not in self['floating_ips']:
            self['floating_ips'].append(floating_ip)

    def floating_ip_addresses(self):
        return [ip['address'] for ip in self['floating_ips']]

    @classmethod
    def hydrate(cls, fixed_ip):
        fixed_ip = FixedIP(**fixed_ip)
        fixed_ip['floating_ips'] = [IP.hydrate(floating_ip)
                                   for floating_ip in fixed_ip['floating_ips']]
        return fixed_ip


class Route(Model):
    def __init__(self, destination=None, netmask=None, gateway=None,
                 interface=None, **kwargs):
        super(Route, self).__init__()

        self['destination'] = destination
        self['netmask'] = netmask
        self['gateway'] = gateway
        self['interface'] = interface

    @classmethod
    def hydrate(cls, route):
        route = Route(**route)
        route['gateway'] = IP.hydrate(route['gateway'])
        return route


class Subnet(Model):
    def __init__(self, cidr=None, dns=None, gateway=None, ips=None,
                 routes=None, **kwargs):
        super(Subnet, self).__init__()

        self['cidr'] = cidr
        self['dns'] = dns or []
        self['gateway'] = gateway
        self['ips'] = ips or []
        self['routes'] = routes or []
        self['version'] = kwargs.get('version')

        if self['cidr'] and not 'version':
            self['version'] = netaddr.IPNetwork(self['cidr']).version

    def __eq__(self, other):
        return self['cidr'] == other['cidr']

    def add_route(self, new_route):
        if new_route not in self['routes']:
            self['routes'].append(new_route)

    def add_dns(self, dns):
        if dns not in self['dns']:
            self['dns'].append(dns)

    def add_ip(self, ip):
        if ip not in self['ips']:
            self['ips'].append(ip)

    @classmethod
    def hydrate(cls, subnet):
        subnet = Subnet(**subnet)
        subnet['dns'] = [IP.hydrate(dns) for dns in subnet['dns']]
        subnet['ips'] = [FixedIP.hydrate(ip) for ip in subnet['ips']]
        subnet['routes'] = [Route.hydrate(route) for route in subnet['routes']]
        subnet['gateway'] = IP.hydrate(subnet['gateway'])
        return subnet


class Network(Model):
    def __init__(self, id=None, bridge=None, label=None, injected=False,
                 vlan=None, bridge_interface=None, multi_host=False,
                 subnets=None, **kwargs):
        super(Network, self).__init__()

        self['id'] = id
        self['bridge'] = bridge
        self['label'] = label
        self['injected'] = injected
        self['vlan'] = vlan
        self['bridge_interface'] = bridge_interface
        self['multi_host'] = multi_host
        self['subnets'] = subnets or []

    def add_subnet(self, subnet):
        if subnet not in self['subnets']:
            self['subnets'].append(subnet)

    @classmethod
    def hydrate(cls, network):
        if network:
            network = Network(**network)
            network['subnets'] = [Subnet.hydrate(subnet)
                                  for subnet in network['subnets']]
        return network


class VIF(Model):
    def __init__(self, id=None, address=None, network=None, *args, **kwargs):
        super(VIF, self).__init__(*args)

        self['id'] = id
        self['address'] = address
        self['network'] = network or None

    def __eq__(self, other):
        return self['id'] == other['id']

    def fixed_ips(self):
        return [fixed_ip for subnet in self['network']['subnets']
                         for fixed_ip in subnet['ips']]

    def floating_ips(self):
        return [floating_ip for fixed_ip in self.fixed_ips()
                            for floating_ip in fixed_ip['floating_ips']]

    def labeled_ips(self):
        # returns this structure:
        # {'label': 'my_network',
        #  'id': 'uuid',
        #  'ips': [{'address': '123.123.123.123',
        #           'version': 4,
        #           'type: 'fixed'},
        #          {'address': '124.124.124.124',
        #           'version': 4,
        #           'type': 'floating'},
        #          {'address': 'fe80::4',
        #           'version': 6,
        #           'type': 'fixed'}]
        if self['network']:
            # remove unecessary fields on fixed_ips
            ips = [IP(**ip) for ip in self.fixed_ips()]
            # add floating ips to list (if any)
            ips.extend(self.floating_ips())
            return {'network_label': self['network']['label'],
                    'network_id': self['network']['id'],
                    'ips': ips}

    @classmethod
    def hydrate(cls, vif):
        vif = VIF(**vif)
        vif['network'] = Network.hydrate(vif['network'])
        return vif


class NetworkInfo(list):
    """Class used to store and manipulate network information within nova"""

    # NetworkInfo is a list of VIFs

    def __init__(self, *args, **kwargs):
        super(NetworkInfo, self).__init__(*args, **kwargs)

    def fixed_ips(self):
        return [IP(**ip) for vif in self for ip in vif.fixed_ips()]

    def floating_ips(self):
        return [ip for vif in self for ip in vif.floating_ips()]

    @classmethod
    def hydrate(cls, network_info):
        if isinstance(network_info, types.StringTypes):
            network_info = json.loads(network_info)
        return NetworkInfo([VIF.hydrate(vif) for vif in network_info])

    def generate_nova_network_cache(self):
        pass


if __name__ == '__main__':
#    s = json.dumps(x)
#    x = FixedIP(**json.loads(s))
#    x.add_floating_ip(f3)
#    print x

    print '\nnetwork info'
    # vif 1
    floating_ip1 = IP(address='123.123.123.123', type='floating')
    floating_ip2 = IP(address='123.123.123.124', type='floating')
    fixed_ip1 = FixedIP(address='10.1.1.5')
    fixed_ip1.add_floating_ip(floating_ip1)
    fixed_ip1.add_floating_ip(floating_ip2)
    dns1 = IP(address='4.2.2.1', type='dns')
    dns2 = IP(address='4.2.2.2', type='dns')
    gw = IP(address='10.1.1.254', type='gateway')
    r = Route(destination='default', netmask='0.0.0.0', gateway=gw)
    s = Subnet(cidr='10.1.1.0/24', gateway=gw)
    s.add_dns(dns1)
    s.add_dns(dns2)
    s.add_route(r)
    s.add_ip(fixed_ip1)
    n = Network(id=1, bridge='xenbr0', label='public')
    n.add_subnet(s)
    v1 = VIF(id=1, address='a:s:d:f', network=n)

    # vif 2
    floating_ip1 = IP(address='125.125.125.125', type='floating')
    floating_ip2 = IP(address='126.126.126.126', type='floating')
    fixed_ip1 = FixedIP(address='10.2.1.5')
    fixed_ip1.add_floating_ip(floating_ip1)
    fixed_ip1.add_floating_ip(floating_ip2)
    dns1 = IP(address='4.2.2.1', type='dns')
    dns2 = IP(address='4.2.2.2', type='dns')
    gw = IP(address='10.2.1.254', type='gateway')
    r1 = Route(destination='10.65.192.0', netmask='255.255.255.192',
               gateway=gw, interface='eth1')
    r2 = Route(destination='10.65.0.0', netmask='255.255.0.0',
               gateway=gw, interface='eth1')
    s = Subnet(cidr='10.2.1.0/24', gateway=gw)
    s.add_dns(dns1)
    s.add_dns(dns2)
    s.add_route(r)
    s.add_ip(fixed_ip1)
    n = Network(id=2, bridge='xenbr2', label='service_net')
    n.add_subnet(s)
    v2 = VIF(id=2, address='z:x:c:v', network=n)

    nw_info = NetworkInfo([v1, v2])
    print nw_info
#    print nw_info.fixed_ips()
#    print nw_info.floating_ips()

    print '\n\n\n\n'
    s = json.dumps(nw_info)
    nw_info = NetworkInfo.hydrate(s)
    print nw_info

    print '\n\n\n\n'
    for vif in nw_info:
        print vif.labeled_ips()

    print '\n\n\n\n'
    v1 = VIF(id=1)
    v2 = VIF(id=2)
    v3 = VIF(id=3)
    nw_info = NetworkInfo([v1, v2, v3])
    print nw_info
    s = json.dumps(nw_info)
    nw_info = NetworkInfo.hydrate(json.loads(s))
    print nw_info
