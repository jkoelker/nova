# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC.
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

import contextlib
import mock

from nova import context
from nova import db
from nova import exception
from nova import flags
from nova.network.melantum import manager
from nova.network.melantum import melange
from nova.network.melantum import quantum_connection
from nova import test
import nova.utils

FLAGS = flags.FLAGS


def dummy(*args, **kwargs):
    pass


def dummy_list(*args, **kwargs):
    return []


def dummy_raise(*args, **kwargs):
    raise test.TestingException('Boom!')


def _ip_addresses_helper(ips_per_vif):
    return ['10.0.0.1%02d' % i for i in xrange(ips_per_vif)]


def _vif_helper(tenant_id, network_uuid, mac_offset=0, vif_id=None,
                name=None):
    network_name = name or 'net%s' % network_uuid
    return {'id': vif_id or str(nova.utils.gen_uuid()),
            'mac_address': '00:00:00:00:00:%02d' % mac_offset,
            'ip_addresses': [
                    {'address': _ip_addresses_helper(1)[0],
                    'ip_block': {'tenant_id': tenant_id,
                                 'network_id': network_uuid,
                                 'network_name': network_name,
                                 'gateway': '10.0.0.1',
                                 'cidr': '10.0.0.0/8',
                                 'dns1': '8.8.8.8',
                                 'dns2': '8.8.4.4',
                                 'ip_routes': [
                                   {'destination': '1.1.1.1',
                                    'gateway': '2.2.2.2',
                                    'netmask': '255.0.0.0'}]}}]}


def _ips_from_vif_stub(ips_per_vif, tenants, networks, names):
    def ips(vif):
        ip_addresses = _ip_addresses_helper(ips_per_vif)
        nets = [n['network_id'] for n in networks]
        return ip_addresses, tenants, nets, names
    return ips


def _fake_networks(network_count, tenant_id):
    """id is the id from melange
    network_id is the id from quantum. Dumb"""
    return [{'id': str(nova.utils.gen_uuid()),
             'name': 'net%d' % i,
             'cidr': '10.0.0.0/8',
             'network_id': str(nova.utils.gen_uuid()),
             'tenant_id': tenant_id} for i in xrange(network_count)]


def _get_allocated_networks_stub(vifs, bare_uuids=True):

    def allocated_nets(self, instance_id):
        if bare_uuids:
            return [{'id': vif} for vif in vifs]
        return vifs

    return allocated_nets


def _allocate_for_instance_networks_stub(networks):
    vif_ids = [str(nova.utils.gen_uuid()) for i in xrange(len(networks))]

    def allocate(self, tenant_id, instance_id, nets):
        # explicitly ignoring including IPs, as we're going to
        # stub out the helper method that iterates over VIFs looking
        # for them.
        return [_vif_helper(tenant_id, networks[i],
                            mac_offset=i, vif_id=vif_ids[i])
                    for i in xrange(len(networks))]
    return vif_ids, allocate


def _create_network_stub(network_uuid):

    def net_create(self, tenant_id, label, nova_id=None):
        return network_uuid
    return net_create


def _get_networks_for_tenant_stub(networks):

    def nets_for_tenant(self, tenant_id):
        return networks
    return nets_for_tenant


def _get_attached_ports_stub(ports):

    def get_ports(self, tenant_id, network_id):
        return ports
    return get_ports


def _create_ip_policy_stub():
    def policy(self, tenant_id, network_id, label):
        return dict(id=1)

    return policy


def _get_port_by_attachment_stub(port):
    def get_port(self, tenant_id, instance_id, interface_id):
        return port
    return get_port


def _quantum_client_stub(networks_dict):
    class Client(object):
        def __init__(self, *args, **kwargs):
            self.tenant = None
            self.format = None

        def do_request(self, method, url):
            return networks_dict
    return Client


def _normalize_network_stub(label):
    def normalize(net):
        net['label'] = label
        return net
    return normalize


def _create_ip_block_stub(block):
    def ip(*args, **kwargs):
        return block
    return ip


@mock.patch('nova.network.melantum.melange.Connection'
            '.get_networks_for_tenant')
@mock.patch('nova.network.melantum.melange.Connection'
            '.get_allocated_networks')
@mock.patch('nova.network.melantum.melange.Connection'
            '.allocate_for_instance_networks')
class MelantumManagerInterfaceTests(test.TestCase):
    """This test suite merely checks that the methods are callable"""
    def setUp(self):
        super(MelantumManagerInterfaceTests, self).setUp()
        self.context = context.RequestContext(user_id=1, project_id=1)
        self.net_manager = manager.MelantumManager()

    @mock.patch('nova.network.melantum.quantum_connection'
                '.QuantumClientConnection.create_and_attach_port')
    def test_allocate_for_instance(self, *args):
        self.net_manager.allocate_for_instance(self.context,
                                               instance_id=1,
                                               rxtx_factor=1,
                                               project_id='project1',
                                               host='host')

    def test_deallocate_for_instance(self, *args):
        self.net_manager.deallocate_for_instance(self.context,
                                                 instance_id=1,
                                                 project_id='project1')

    def test_get_all_networks(self, *args):
        self.net_manager.get_all_networks(self.context)

    def test_init_host(self, *args):
        self.net_manager.init_host()


class MelantumManagerTestsAllocateForInstanceGlobalIDs(test.TestCase):
    def setUp(self):
        super(MelantumManagerTestsAllocateForInstanceGlobalIDs, self).setUp()

        self.flags(network_global_uuid_label_map=[
            '00000000-0000-0000-0000-000000000000', 'public',
            '11111111-1111-1111-1111-111111111111', 'private'])

        self.tenant_id = 'project1'
        self.context = context.RequestContext(user_id=1,
                                              project_id=self.tenant_id)
        self.q_client = ('nova.network.melantum.quantum_connection.'
                         'QuantumClientConnection')
        self.m_client = ('nova.network.melantum.melange.Connection')

        self.default_networks = _fake_networks(2, self.tenant_id)

        def iterlabel():
            for label in ['public', 'private']:
                yield label
        self.label_toggler = iterlabel()

        def pub_priv(s, network):
            network = {'id': network['network_id'],
                       'cidr': network['cidr']}
            try:
                network['label'] = self.label_toggler.next()
            except StopIteration:
                self.label_toggler = iterlabel()
                network['label'] = self.label_toggler.next()

            return network

        self.stubs.Set(manager.MelantumManager, '_normalize_network', pub_priv)
        self.stubs.Set(melange.Connection,
                       'get_networks_for_tenant',
                       lambda *args, **kwargs: self.default_networks)
        self.net_manager = manager.MelantumManager()
        self.normalized_networks = [self.net_manager._normalize_network(n)
                                    for n in self.default_networks]

    def test_nw_map(self):
        pub_uuid = [nw['id'] for nw in self.normalized_networks
                             if nw['label'] == 'public'][0]
        priv_uuid = [nw['id'] for nw in self.normalized_networks
                              if nw['label'] == 'private'][0]
        should_be = {'00000000-0000-0000-0000-000000000000': pub_uuid,
                     '11111111-1111-1111-1111-111111111111': priv_uuid,
                     pub_uuid: '00000000-0000-0000-0000-000000000000',
                     priv_uuid: '11111111-1111-1111-1111-111111111111'}
        self.assertEqual(self.net_manager._nw_map, should_be)

    def test_get_all_networks(self):
        nets = self.net_manager.get_all_networks(self.context)
        should_be = self.normalized_networks
        for nw in should_be:
            if nw['label'] == 'public':
                nw['id'] = '00000000-0000-0000-0000-000000000000'
            elif nw['label'] == 'private':
                nw['id'] = '11111111-1111-1111-1111-111111111111'
        self.assertEqual(nets, should_be)

    def test_allocate_for_instance_with_global_requested_nets(self):
        with contextlib.nested(
            mock.patch.object(self.net_manager, '_vifs_to_model'),
            mock.patch(self.q_client + '.create_and_attach_port'),
            mock.patch(self.m_client + '.get_networks_for_tenant'),
            mock.patch(self.m_client + '.allocate_for_instance_networks'),
            ) as (vifs_to_model,
                  create_and_attach,
                  get_networks_for_tenant,
                  allocate_for_instance_networks):

            # only take the first network for the test
            networks = _fake_networks(2, self.tenant_id)
            expected_networks = networks[:1]
            requested_networks = [n['network_id']
                                  for n in expected_networks]
            requested_networks.append('0000000000-0000-0000-0000-000000000000')

            vifs = [_vif_helper(self.tenant_id, n['network_id'])
                    for n in expected_networks]
            get_networks_for_tenant.return_value = networks
            allocate_for_instance_networks.return_value = vifs

            instance_id = 1
            kwargs = dict(instance_id=instance_id,
                          rxtx_factor=1,
                          project_id='project1',
                          requested_networks=[requested_networks],
                          host='host')

            self.net_manager.allocate_for_instance(self.context, **kwargs)

            args = (self.tenant_id,
                    instance_id,
                    [{'id': n['network_id'], 'tenant_id': n['tenant_id']}
                      for n in expected_networks])
            allocate_for_instance_networks.assert_called_once_with(*args)
            self.assertTrue(create_and_attach.called)


class MelantumManagerTestsAllocateForInstance(test.TestCase):
    @mock.patch('nova.network.melantum.manager.MelantumManager'
                '._vifs_to_model')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_networks_for_tenant')
    @mock.patch('nova.network.melantum.quantum_connection'
                '.QuantumClientConnection.create_and_attach_port')
    def test_allocate_for_instance_with_vifs(self, create_and_attach,
                                             get_networks_for_tenant,
                                             allocate_for_instance_networks,
                                             vifs_to_model):
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        net_manager = manager.MelantumManager()
        networks = _fake_networks(1, tenant_id)
        vifs = [_vif_helper(tenant_id, n['network_id'])
                for n in networks]
        get_networks_for_tenant.return_value = networks
        allocate_for_instance_networks.return_value = vifs

        net_manager.allocate_for_instance(ctx,
                                          instance_id=1,
                                          rxtx_factor=1,
                                          project_id=tenant_id,
                                          host='host')
        create_and_attach.assert_called()

    @mock.patch('nova.network.melantum.manager.MelantumManager'
                '._vifs_to_model')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_networks_for_tenant')
    @mock.patch('nova.network.melantum.quantum_connection'
                '.QuantumClientConnection.create_and_attach_port')
    def test_allocate_for_instance_with_requested_nets(self,
                                             create_and_attach,
                                             get_networks_for_tenant,
                                             allocate_for_instance_networks,

                                             vifs_to_model):
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        net_manager = manager.MelantumManager()
        # only take the first network for the test
        networks = _fake_networks(2, tenant_id)
        expected_networks = networks[:1]
        requested_networks = [n['network_id']
                              for n in expected_networks]

        vifs = [_vif_helper(tenant_id, n['network_id'])
                for n in expected_networks]
        get_networks_for_tenant.return_value = networks
        allocate_for_instance_networks.return_value = vifs

        instance_id = 1
        kwargs = dict(instance_id=instance_id,
                      rxtx_factor=1,
                      project_id=tenant_id,
                      requested_networks=[requested_networks],
                      host='host')

        net_manager.allocate_for_instance(ctx, **kwargs)

        args = (tenant_id,
                instance_id,
                [{'id': n['network_id'], 'tenant_id': n['tenant_id']}
                 for n in expected_networks])
        allocate_for_instance_networks.assert_called_once_with(*args)
        create_and_attach.assert_called()

    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_networks_for_tenant')
    @mock.patch('nova.network.melantum.quantum_connection'
                '.QuantumClientConnection.create_and_attach_port')
    def test_allocate_for_instance_no_vifs_raises(self,
                                              create_and_attach,
                                              get_networks_for_tenant,
                                              allocate_for_instance_networks):
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        net_manager = manager.MelantumManager()
        networks = _fake_networks(1, tenant_id)
        get_networks_for_tenant.return_value = networks
        allocate_for_instance_networks.return_value = []

        net_manager.allocate_for_instance(ctx,
                                          instance_id=1,
                                          rxtx_factor=1,
                                          project_id=tenant_id,
                                          host='host')
        self.assertFalse(create_and_attach.called)

    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_networks_for_tenant')
    def test_allocate_for_instance_melange_allocation_fails(self,
                                              get_networks_for_tenant,
                                              allocate_for_instance_networks):
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        get_networks_for_tenant.return_value = []

        def side_effect(*args):
            def clean_up_call(*args, **kwargs):
                return

            allocate_for_instance_networks.side_effect = clean_up_call
            raise test.TestingException()

        allocate_for_instance_networks.side_effect = side_effect

        net_manager = manager.MelantumManager()
        self.assertRaises(test.TestingException,
                          net_manager.allocate_for_instance,
                          ctx, instance_id=1,
                          rxtx_factor=1,
                          project_id=tenant_id,
                          host='host')

    @mock.patch('nova.network.melantum.manager.MelantumManager'
                '._get_ips_and_ids_from_vif')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_networks_for_tenant')
    def test_allocate_for_instance_too_many_net_tenant_ids_fails(self,
                                              get_networks_for_tenant,
                                              allocate_for_instance_networks,
                                              _get_ips_and_ids_from_vif):
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        net_manager = manager.MelantumManager()
        networks = _fake_networks(1, tenant_id)
        vifs = [_vif_helper(tenant_id, n['network_id'])
                for n in networks]
        names = [n['name'] for n in networks]
        ips = _ips_from_vif_stub(ips_per_vif=2,
                                 tenants=[tenant_id, 'project2'],
                                 networks=networks,
                                 names=names)

        allocate_for_instance_networks.return_value = vifs
        get_networks_for_tenant.return_value = networks
        _get_ips_and_ids_from_vif.side_effect = ips

        self.assertRaises(exception.VirtualInterfaceCreateException,
                          net_manager.allocate_for_instance,
                          ctx,
                          instance_id=1,
                          rxtx_factor=1,
                          project_id=tenant_id,
                          host='host')

    @mock.patch('nova.network.melantum.manager.MelantumManager'
                '._get_ips_and_ids_from_vif')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_networks_for_tenant')
    def test_allocate_for_instance_too_many_net_ids_fails(self,
                                              get_networks_for_tenant,
                                              allocate_for_instance_networks,
                                              _get_ips_and_ids_from_vif):
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        net_manager = manager.MelantumManager()
        networks = _fake_networks(1, tenant_id)
        vifs = [_vif_helper(tenant_id, n['network_id'])
                for n in networks]
        names = [n['name'] for n in networks]
        ips = _ips_from_vif_stub(ips_per_vif=2,
                                 tenants=[tenant_id],
                                 networks=networks * 2,
                                 names=names * 2)
        get_networks_for_tenant.return_value = networks
        allocate_for_instance_networks.return_value = vifs
        _get_ips_and_ids_from_vif.side_effect = ips

        self.assertRaises(exception.VirtualInterfaceCreateException,
                          net_manager.allocate_for_instance,
                          ctx,
                          instance_id=1,
                          rxtx_factor=1,
                          project_id=tenant_id,
                          host='host')

    @mock.patch('nova.network.melantum.manager.MelantumManager'
                '._get_ips_and_ids_from_vif')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_networks_for_tenant')
    def test_allocate_for_instance_no_net_tenant_ids_fails(self,
                                              get_networks_for_tenant,
                                              allocate_for_instance_networks,
                                              _get_ips_and_ids_from_vif):
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        net_manager = manager.MelantumManager()
        networks = _fake_networks(1, tenant_id)
        vifs = [_vif_helper(tenant_id, n['network_id'])
                for n in networks]
        names = [n['name'] for n in networks]
        ips = _ips_from_vif_stub(ips_per_vif=2,
                                 tenants=[],
                                 networks=networks,
                                 names=names)

        get_networks_for_tenant.return_value = networks
        allocate_for_instance_networks.return_value = vifs
        _get_ips_and_ids_from_vif.side_effect = ips

        self.assertRaises(exception.VirtualInterfaceCreateException,
                          net_manager.allocate_for_instance,
                          ctx,
                          instance_id=1,
                          rxtx_factor=1,
                          project_id=tenant_id,
                          host='host')

    @mock.patch('nova.network.melantum.manager.MelantumManager'
                '._get_ips_and_ids_from_vif')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_networks_for_tenant')
    def test_allocate_for_instance_no_net_ids_fails(self,
                                              get_networks_for_tenant,
                                              allocate_for_instance_networks,
                                              _get_ips_and_ids_from_vif):

        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        net_manager = manager.MelantumManager()
        networks = _fake_networks(1, tenant_id)
        vifs = [_vif_helper(tenant_id, n['network_id'])
                for n in networks]
        ips = _ips_from_vif_stub(ips_per_vif=2,
                                 tenants=[tenant_id],
                                 networks=[],
                                 names=[])

        get_networks_for_tenant.return_value = networks
        allocate_for_instance_networks.return_value = vifs
        _get_ips_and_ids_from_vif.side_effect = ips

        self.assertRaises(exception.VirtualInterfaceCreateException,
                          net_manager.allocate_for_instance,
                          ctx,
                          instance_id=1,
                          rxtx_factor=1,
                          project_id=tenant_id,
                          host='host')

    @mock.patch('nova.network.melantum.manager.MelantumManager'
                '._generate_address_pairs')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_networks_for_tenant')
    @mock.patch('nova.network.melantum.quantum_connection'
                '.QuantumClientConnection.create_and_attach_port')
    def test_allocate_for_instance_with_port_security(self,
                                              create_and_attach,
                                              get_networks_for_tenant,
                                              allocate_for_instance_networks,
                                              gen_pairs):
        self.flags(quantum_use_port_security=True)
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        net_manager = manager.MelantumManager()
        networks = _fake_networks(1, tenant_id)
        vifs = [_vif_helper(tenant_id, n['network_id'])
                for n in networks]

        get_networks_for_tenant.return_value = networks
        allocate_for_instance_networks.return_value = vifs

        net_manager.allocate_for_instance(ctx,
                                          instance_id=1,
                                          rxtx_factor=1,
                                          project_id=tenant_id,
                                          host='host')
        create_and_attach.assert_called()
        gen_pairs.assert_called()

    @mock.patch('nova.network.melantum.manager.MelantumManager'
                '._generate_address_pairs')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_networks_for_tenant')
    @mock.patch('nova.network.melantum.quantum_connection'
                '.QuantumClientConnection.create_and_attach_port')
    @mock.patch('netaddr.EUI')
    def test_allocate_for_instance_with_port_security_link_local(self,
                                              eui,
                                              create_and_attach,
                                              get_networks_for_tenant,
                                              allocate_for_instance_networks,
                                              gen_pairs):
        self.flags(quantum_use_port_security=True)
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        net_manager = manager.MelantumManager()
        networks = _fake_networks(1, tenant_id)
        vifs = [_vif_helper(tenant_id, n['network_id'])
                for n in networks]

        get_networks_for_tenant.return_value = networks
        allocate_for_instance_networks.return_value = vifs

        net_manager.allocate_for_instance(ctx,
                                          instance_id=1,
                                          rxtx_factor=1,
                                          project_id=tenant_id,
                                          host='host')
        create_and_attach.assert_called()
        gen_pairs.assert_called()


class MelantumManagerDeallocateForInstance(test.TestCase):

    @mock.patch('nova.network.melantum.manager.MelantumManager'
                '._deallocate_port')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_allocated_networks')
    def test_deallocate_instance_no_vifs(self, get_allocated_networks,
                                         allocate_for_instance_networks,
                                         deallocate_port):
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        get_allocated_networks.return_value = []
        net_manager = manager.MelantumManager()

        net_manager.deallocate_for_instance(context=ctx,
                                            instance_id=1,
                                            project_id=tenant_id)
        self.assertFalse(deallocate_port.called)

    @mock.patch('nova.network.melantum.manager.MelantumManager'
                '._deallocate_port')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_allocated_networks')
    def test_deallocate_instance(self, get_allocated_networks,
                                 allocate_for_instance_networks,
                                 deallocate_port):
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        vifs = [_vif_helper(tenant_id, n['network_id'])
                for n in _fake_networks(1, tenant_id)]
        get_allocated_networks.return_value = vifs
        net_manager = manager.MelantumManager()

        net_manager.deallocate_for_instance(context=ctx,
                                            instance_id=1,
                                            project_id=tenant_id)

        self.assertTrue(deallocate_port.called)

    @mock.patch('nova.network.melantum.manager.MelantumManager'
                '._deallocate_port')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.allocate_for_instance_networks')
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_allocated_networks')
    def test_deallocate_instance_deallocate_port_fails(self,
                                           get_allocated_networks,
                                           allocate_for_instance_networks,
                                           deallocate_port):
        tenant_id = 'project1'
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)
        vifs = [_vif_helper(tenant_id, n['network_id'])
                for n in _fake_networks(1, tenant_id)]
        get_allocated_networks.return_value = vifs
        net_manager = manager.MelantumManager()

        deallocate_port.side_effect = Exception('Boom!')
        net_manager.deallocate_for_instance(ctx, 1, tenant_id)


class MelantumManagerCreateNetworks(test.TestCase):
    def test_create_networks(self):
        net_manager = manager.MelantumManager()
        network_uuid = nova.utils.gen_uuid()
        stub = self.stubs.Set
        ctx = context.RequestContext(user_id=1, project_id='project1')
        stub(net_manager, '_normalize_network',
             _normalize_network_stub('label'))
        stub(melange.Connection,
             'create_unusable_octet_in_policy', dummy)
        stub(quantum_connection.QuantumClientConnection,
             'create_network', _create_network_stub(network_uuid))
        stub(melange.Connection,
             'create_ip_policy', _create_ip_policy_stub())
        stub(melange.Connection,
             'create_unusable_octet_in_policy', dummy)
        stub(melange.Connection,
                       'create_ip_block', _create_ip_block_stub({}))

        ret = net_manager.create_networks(ctx, label='label',
                                          cidr='10.0.0.0/24')
        self.assertEqual(ret, [{'label': 'label'}])


class MelantumManagerDeleteNetwork(test.TestCase):
    def setUp(self):
        super(MelantumManagerDeleteNetwork, self).setUp()
        self.tenant_id = 'project1'
        self.context = context.RequestContext(user_id=1,
                                              project_id=self.tenant_id)
        self.net_manager = manager.MelantumManager()
        self.networks = _fake_networks(network_count=2,
                                       tenant_id=self.tenant_id)
        stub = self.stubs.Set

        stub(melange.Connection, 'get_networks_for_tenant',
             _get_networks_for_tenant_stub(self.networks))
        stub(quantum_connection.QuantumClientConnection, 'get_attached_ports',
             _get_attached_ports_stub([]))
        stub(quantum_connection.QuantumClientConnection, 'delete_network',
             dummy)

    def test_delete_network_no_networks_raises(self):
        self.assertRaises(exception.NetworkNotFound,
                          self.net_manager.delete_network,
                          context=self.context,
                          uuid='wharrgarbl')

    def test_delete_network_too_many_networks_raises(self):
        network_uuid = self.networks[0]['network_id']
        # Make the ids the same, so we find two of the same net
        self.networks[1]['network_id'] = network_uuid
        self.assertRaises(exception.NetworkFoundMultipleTimes,
                          self.net_manager.delete_network,
                          context=self.context,
                          uuid=network_uuid)

    def test_delete_network_active_ports_raises(self):
        self.stubs.Set(quantum_connection.QuantumClientConnection,
                       'get_attached_ports',
                       _get_attached_ports_stub(['port']))
        network_uuid = self.networks[0]['network_id']
        self.assertRaises(exception.NetworkBusy,
                          self.net_manager.delete_network,
                          context=self.context,
                          uuid=network_uuid)

    def test_delete_networK(self):
        network_uuid = self.networks[0]['network_id']
        with mock.patch('nova.network.melantum.melange.Connection.'
                        'delete_ip_block') as patch:
            self.net_manager.delete_network(context=self.context,
                                            uuid=network_uuid)
            patch.assert_called()


class MelantumManagerGetAllNetworks(test.TestCase):
    def setUp(self):
        super(MelantumManagerGetAllNetworks, self).setUp()
        self.tenant_id = 'project1'
        self.net_manager = manager.MelantumManager()
        stub = self.stubs.Set
        self.context = context.RequestContext(user_id=1,
                                      project_id='project1')
        self.networks = _fake_networks(network_count=2,
                                       tenant_id=self.tenant_id)
        stub(melange.Connection, 'get_networks_for_tenant',
             _get_networks_for_tenant_stub(self.networks))
        stub(self.net_manager, '_normalize_network',
             _normalize_network_stub('label'))

    def test_get_all_networks_no_tenant(self):
        nets = self.net_manager.get_all_networks(self.context)
        self.assertEqual(nets, self.networks)


class MelantumManagerGetInstanceNwInfo(test.TestCase):
    def setUp(self):
        super(MelantumManagerGetInstanceNwInfo, self).setUp()
        self.q_client = ('nova.network.melantum.quantum_connection.'
                         'QuantumClientConnection')
        self.m_client = ('nova.network.melantum.melange.Connection')

    def test_get_instance_nw_info(self):
        tenant_id = 'project1'
        net_manager = manager.MelantumManager()
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)

        with mock.patch(self.m_client + '.get_allocated_networks'
                       ) as get_allocated_networks:

            networks = _fake_networks(2, tenant_id)
            vifs = [_vif_helper(tenant_id, n['network_id'])
                    for n in networks]

            get_allocated_networks.return_value = vifs

            get_nw_info = net_manager.get_instance_nw_info
            res = get_nw_info(ctx, instance_id=1, project_id=tenant_id)
            self.assertEqual(len(res), len(vifs))

    def test_get_instance_nw_info_correct_order(self):
        tenant_id = 'project1'
        net_manager = manager.MelantumManager()
        ctx = context.RequestContext(user_id=1, project_id=tenant_id)

        networks = _fake_networks(2, tenant_id)
        vifs = [_vif_helper(tenant_id, networks[-1]['network_id'],
                            name='net1'),
                _vif_helper(tenant_id, networks[0]['network_id'],
                            name='net0')]

        network_order = ['net%d' % i for i in xrange(len(networks))]
        self.flags(network_order=network_order)

        with mock.patch(self.m_client + '.get_allocated_networks'
                        ) as get_allocated_networks:

            get_allocated_networks.return_value = vifs

            get_nw_info = net_manager.get_instance_nw_info
            res = get_nw_info(ctx, instance_id=1, project_id=tenant_id)

            self.assertEqual(len(res), len(vifs))
            self.assertEqual(res[0]['network']['label'],
                             networks[0]['name'])
            self.assertEqual(res[1]['network']['label'],
                             networks[-1]['name'])


class MelantumManagerGetIpsAndIdsFromVifs(test.TestCase):
    def test_get_ips_and_ids_from_vifs(self):
        tenant_id = 'project1'
        net_manager = manager.MelantumManager()
        network_uuid = str(nova.utils.gen_uuid())
        network_name = 'net%s' % network_uuid

        vif = _vif_helper(tenant_id, network_uuid)

        res = net_manager._get_ips_and_ids_from_vif(vif)
        addresses, tenants, network_uuids, network_names = res

        self.assertEquals(addresses, ['10.0.0.100'])
        self.assertEquals(tenants, set(['project1']))
        self.assertEquals(network_uuids, set([network_uuid]))
        self.assertEquals(network_names, set([network_name]))


class MelantumManagerCleanUpMelange(test.TestCase):
    def setUp(self):
        super(MelantumManagerCleanUpMelange, self).setUp()
        self.tenant_id = 'project1'
        self.net_manager = manager.MelantumManager()

    def test_clean_up_melange(self):
        with mock.patch('nova.network.melantum.melange.Connection.'
                        'allocate_for_instance_networks'):
            self.net_manager._clean_up_melange(self.tenant_id,
                                               instance_id=1,
                                               raise_exception=False)

    def test_clean_up_melange_no_exception_doesnt_raise(self):
        with mock.patch('nova.network.melantum.melange.Connection.'
                        'allocate_for_instance_networks'):
            self.net_manager._clean_up_melange(self.tenant_id,
                                               instance_id=1,
                                               raise_exception=True)

    def test_clean_up_melange_exception_raise_exception_true_raises(self):
        with mock.patch('nova.network.melantum.melange.Connection.'
                        'allocate_for_instance_networks') as allocate:
            allocate.side_effect = test.TestingException('Boom!')
            self.assertRaises(test.TestingException,
                              self.net_manager._clean_up_melange,
                              self.tenant_id,
                              instance_id=1,
                              raise_exception=True)

    def test_clean_up_melange_exception_raise_exception_false(self):
        with mock.patch('nova.network.melantum.melange.Connection.'
                        'allocate_for_instance_networks') as allocate:
            allocate.side_effect = exception.MelangeConnectionFailed()
            self.net_manager._clean_up_melange(self.tenant_id,
                                               instance_id=1,
                                               raise_exception=False)


class MelantumManagerGenerateAddressPairs(test.TestCase):
    def test_generate_address_pairs(self):
        net_manager = manager.MelantumManager()
        network_uuid = str(nova.utils.gen_uuid())

        vif = _vif_helper('project1', network_uuid)
        ips = _ip_addresses_helper(1)
        res = net_manager._generate_address_pairs(vif, ips)

        self.assertEquals(res[0]['ip_address'], '10.0.0.100')
        self.assertEquals(res[0]['mac_address'], '00:00:00:00:00:00')


class MelantumManagerDeallocatePort(test.TestCase):
    def setUp(self):
        super(MelantumManagerDeallocatePort, self).setUp()
        self.tenant_id = 'project1'
        self.net_manager = manager.MelantumManager()
        self.network_uuid = str(nova.utils.gen_uuid())
        self.stubs.Set(quantum_connection.QuantumClientConnection,
             'get_port_by_attachment', _get_port_by_attachment_stub('port'))

    def test_deallocate_port_no_port(self):
        self.stubs.Set(quantum_connection.QuantumClientConnection,
             'get_port_by_attachment', _get_port_by_attachment_stub(None))
        with mock.patch('nova.network.melantum.quantum_connection.'
                        'QuantumClientConnection.detach_and_delete_port') \
                    as patch:
            self.net_manager._deallocate_port(self.tenant_id,
                                              self.network_uuid,
                                              interface_id=1)
            self.assertEqual(patch.called, False)

    def test_deallocate_port(self):
        with mock.patch('nova.network.melantum.quantum_connection.'
                        'QuantumClientConnection.'
                        'detach_and_delete_port') as patch:
            self.net_manager._deallocate_port(self.tenant_id,
                                              self.network_uuid,
                                              interface_id=1)
            self.assertTrue(patch.called)


class MelantumManagerVifFromNetwork(test.TestCase):
    def setUp(self):
        super(MelantumManagerVifFromNetwork, self).setUp()
        self.tenant_id = 'project1'
        self.label = 'public'
        self.net_manager = manager.MelantumManager()
        self.network_uuid = str(nova.utils.gen_uuid())

    def test_vif_from_network(self):
        vifs = _vif_helper(self.tenant_id, self.network_uuid)
        res = self.net_manager._vif_from_network(vifs, self.network_uuid,
                                                 self.label)
        self.assertEquals(res['network']['subnets'][0]['ips'][0]['address'],
                          '10.0.0.100')

    def test_vif_from_network_no_gateway(self):
        vifs = _vif_helper(self.tenant_id, self.network_uuid)
        vifs['ip_addresses'][0]['ip_block'].pop('gateway')
        res = self.net_manager._vif_from_network(vifs, self.network_uuid,
                                                 self.label)
        self.assertEqual(res['network']['subnets'][0].get('gateway'), None)

    def test_vif_from_network_no_dns(self):
        vifs = _vif_helper(self.tenant_id, self.network_uuid)
        vifs['ip_addresses'][0]['ip_block'].pop('dns1')
        vifs['ip_addresses'][0]['ip_block'].pop('dns2')
        res = self.net_manager._vif_from_network(vifs, self.network_uuid,
                                                 self.label)
        self.assertEqual(res['network']['subnets'][0].get('dns'), [])


class MelantumManagerVifsToModel(test.TestCase):
    def setUp(self):
        super(MelantumManagerVifsToModel, self).setUp()
        self.tenant_id = 'project1'
        self.net_manager = manager.MelantumManager()
        self.networks = _fake_networks(network_count=1,
                                       tenant_id=self.tenant_id)
        self.names = [n['name'] for n in self.networks]
        self.vif = _vif_helper(self.tenant_id, self.networks[0]['id'])

        self.patcher = mock.patch.object(self.net_manager,
                                         '_get_ips_and_ids_from_vif')
        self.ips_from_vif = self.patcher.start()
        self.ips_from_vif.side_effect = _ips_from_vif_stub(
                                            ips_per_vif=2,
                                            tenants=[self.tenant_id],
                                            networks=self.networks,
                                            names=self.names)

    def tearDown(self):
        self.patcher.stop()
        super(MelantumManagerVifsToModel, self).tearDown()

    def test_vifs_to_model_no_network_ids_fails(self):
        self.ips_from_vif.side_effect = _ips_from_vif_stub(
                                            ips_per_vif=2,
                                            tenants=[self.tenant_id],
                                            networks=[],
                                            names=self.names)
        self.assertRaises(exception.VirtualInterfaceIntegrityException,
                          self.net_manager._vifs_to_model, [self.vif])

    def test_vifs_to_model_no_tenant_ids_fails(self):
        self.ips_from_vif.side_effect = _ips_from_vif_stub(
                                            ips_per_vif=2,
                                            tenants=[],
                                            networks=self.networks,
                                            names=self.names)
        self.assertRaises(exception.VirtualInterfaceIntegrityException,
                self.net_manager._vifs_to_model, [self.vif])

    def test_vifs_to_model_too_many_networks_fails(self):
        networks = _fake_networks(network_count=4,
                                  tenant_id=self.tenant_id)
        names = [n['name'] for n in networks]
        self.ips_from_vif.side_effect = _ips_from_vif_stub(
                                            ips_per_vif=2,
                                            tenants=[self.tenant_id],
                                            networks=networks,
                                            names=names)
        self.assertRaises(exception.VirtualInterfaceIntegrityException,
                          self.net_manager._vifs_to_model, [self.vif])

    def test_vifs_to_model_too_many_tenants_fails(self):
        networks = _fake_networks(network_count=4,
                tenant_id=self.tenant_id)
        names = [n['name'] for n in networks]
        self.ips_from_vif.side_effect = _ips_from_vif_stub(
                                            ips_per_vif=2,
                                            tenants=[self.tenant_id] * 4,
                                            networks=networks,
                                            names=names)
        self.assertRaises(exception.VirtualInterfaceIntegrityException,
                self.net_manager._vifs_to_model, [self.vif])

    def test_vifs_to_model(self):
        res = self.net_manager._vifs_to_model([self.vif])
        self.assertEquals(res[0]['network']['subnets'][0]['ips'][0]['address'],
                          '10.0.0.100')


class MelantumGetInstanceUUIDS(test.TestCase):
    @mock.patch('nova.network.melantum.melange.Connection'
                '.get_instance_ids_by_ip_address')
    @mock.patch.object(db, 'instance_get_by_uuid')
    def test_get_instance_uuids_by_ip_filter(self, instance_get_by_uuid,
                                             get_instance_ids_by_ip_address):
        ctx = context.RequestContext(user_id=1, project_id=1)
        filters = {'ip': 'ip_address'}

        instance = mock.MagicMock()
        instance.uuid = 'instance_uuid'

        instance_get_by_uuid.return_value = instance
        get_instance_ids_by_ip_address.return_value = ['instance_id']

        net_manager = manager.MelantumManager()
        uuids = net_manager.get_instance_uuids_by_ip_filter(ctx, filters)

        self.assertTrue(instance_get_by_uuid.called)
        self.assertTrue(get_instance_ids_by_ip_address.called)
        self.assertEquals(uuids, [{'instance_uuid': 'instance_uuid'}])
