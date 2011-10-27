# Copyright (C) 2011 Midokura KK
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

import copy
import json
import webob

from nova import compute
from nova import network
from nova import test
from nova import utils
from nova.tests.api.openstack import fakes


def get_vifs_by_instance(self, context, server_id):
    vifs = [{'uuid': '00000000-0000-0000-0000-00000000000000000',
             'address': '00-00-00-00-00-00'},
            {'uuid': '11111111-1111-1111-1111-11111111111111111',
             'address': '11-11-11-11-11-11',
             'network_id': '1111'}]
    return copy.deepcopy(vifs)


def get_vif(self, context, vif_id):
    vifs = [vif
            for vif in get_vifs_by_instance(self, context, vif_id)
            if vif['uuid'] == vif_id]
    if not vifs:
        return None
    return vifs[0]


def routing_get(self, context, server_id):
    return {}


class ServerVirtualInterfaceTest(test.TestCase):

    def setUp(self):
        super(ServerVirtualInterfaceTest, self).setUp()
        self.stubs.Set(network.api.API, "get_vif", get_vif)
        self.maxDiff = 1000

    def tearDown(self):
        super(ServerVirtualInterfaceTest, self).tearDown()

    def test_get_virtual_interfaces_list(self):
        self.stubs.Set(network.api.API, "get_vifs_by_instance",
                       get_vifs_by_instance)
        self.stubs.Set(compute.api.API, "routing_get", routing_get)
        url = '/v1.1/123/servers/abcd/os-virtual-interfaces'
        req = webob.Request.blank(url)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)
        response = {'virtual_interfaces': [
                        {'id': '00000000-0000-0000-0000-00000000000000000',
                         'mac_address': '00-00-00-00-00-00',
                         'network_id': None},
                        {'id': '11111111-1111-1111-1111-11111111111111111',
                         'mac_address': '11-11-11-11-11-11',
                         'network_id': '1111'}]}
        self.assertEqual(res_dict, response)

    def test_cache_get_virtual_interfaces_list(self):
        def fake_cache(*args, **kwargs):
            vifs = get_vifs_by_instance(None, None, None)
            for vif in vifs:
                vif['id'] = vif['uuid']
                vif['network'] = {'id': vif.get('network_id')}
                if 'network_id' in vif:
                    del vif['network_id']
            nw_info = {'network_info': utils.dumps(vifs)}
            return {'instance_info_caches': nw_info}

        self.stubs.Set(compute.api.API, "routing_get", fake_cache)
        url = '/v1.1/123/servers/abcd/os-virtual-interfaces'
        req = webob.Request.blank(url)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)
        response = {'virtual_interfaces': [
                        {'id': '00000000-0000-0000-0000-00000000000000000',
                         'mac_address': '00-00-00-00-00-00',
                         'network_id': None},
                        {'id': '11111111-1111-1111-1111-11111111111111111',
                         'mac_address': '11-11-11-11-11-11',
                         'network_id': '1111'}]}
        self.assertDictEqual(res_dict, response)

    def test_get_vif(self):
        self.stubs.Set(network.api.API, "get_vifs_by_instance",
                       get_vifs_by_instance)
        self.stubs.Set(compute.api.API, "routing_get", routing_get)
        vif = '00000000-0000-0000-0000-00000000000000000'
        url = '/v1.1/123/servers/abcd/os-virtual-interfaces/' + vif
        req = webob.Request.blank(url)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)
        response = {'id': '00000000-0000-0000-0000-00000000000000000',
                    'mac_address': '00-00-00-00-00-00',
                    'network_id': None}
        self.assertEqual(res_dict, response)

    def test_cache_get_vif(self):
        def routing_get(*args, **kwargs):
            vifs = get_vifs_by_instance(None, None, None)
            nw_info = {'network_info': utils.dumps(vifs)}
            return {'instance_info_caches': nw_info}

        self.stubs.Set(compute.api.API, "routing_get", routing_get)
        vif = '00000000-0000-0000-0000-00000000000000000'
        url = '/v1.1/123/servers/abcd/os-virtual-interfaces/' + vif
        req = webob.Request.blank(url)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)
        response = {'id': '00000000-0000-0000-0000-00000000000000000',
                    'mac_address': '00-00-00-00-00-00',
                    'network_id': None}
        self.assertEqual(res_dict, response)

    def test_delete_vif(self):
        called = {'remove': False}

        def fake_remove_vif(*args, **kwargs):
            called['remove'] = True

        self.stubs.Set(network.api.API, "remove_vif", fake_remove_vif)
        vif = '00000000-0000-0000-0000-00000000000000000'
        url = '/v1.1/123/servers/abcd/os-virtual-interfaces/' + vif
        req = webob.Request.blank(url)
        req.method = 'DELETE'
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)
        self.assertTrue(called['remove'])

    def test_create_vif(self):
        called = {'add': False}

        def fake_add_vif(self, context, server_id, network_id):
            called['add'] = True
            return {'id': '22222222-2222-2222-2222-22222222222222222',
                    'address': '22-22-22-22-22-22',
                    'network_id': network_id}

        self.stubs.Set(network.api.API, "add_vif", fake_add_vif)
        url = '/v1.1/123/servers/abcd/os-virtual-interfaces'
        req = webob.Request.blank(url)
        req.method = 'POST'
        req.body = json.dumps({'network_id': 'herp'})
        req.headers['Content-Type'] = 'application/json'
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        self.assertTrue(called['add'])
