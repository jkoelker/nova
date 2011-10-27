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

"""The virtual interfaces extension."""

import webob
from webob import exc

from nova import compute
from nova import log as logging
from nova import network
from nova.api.openstack import common
from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova.network import model


LOG = logging.getLogger("nova.api.virtual_interfaces")


def _translate_vif_summary_view(vif):
    """Maps keys for VIF summary view."""
    d = {}
    if "uuid" in vif:
        d['id'] = vif['uuid']
    else:
        d['id'] = vif['id']

    if 'network_id' in vif:
        d['network_id'] = vif['network_id']
    elif 'network' in vif and vif['network'] is not None:
        d['network_id'] = vif['network']['id']
    else:
        d['network_id'] = None

    d['mac_address'] = vif['address']
    return d


def _get_metadata():
    metadata = {
        "attributes": {
                'virtual_interface': ["id", "mac_address"]}}
    return metadata


class ServerVirtualInterfaceController(object):
    """The instance VIF API controller for the Openstack API.
    """

    def __init__(self):
        self.compute_api = compute.API()
        self.network_api = network.API()
        super(ServerVirtualInterfaceController, self).__init__()

    def _items(self, context, server_id):
        """Returns a list of VIFs"""
        return self.network_api.get_vifs_by_instance(context, server_id)

    def _cached_items(self, context, server_id, vif_id=None):
        """Returns the cached list of VIFs"""
        instance = self.compute_api.routing_get(context, server_id)
        json_cache = instance['instance_info_caches']['network_info']
        vifs = model.NetworkInfo.hydrate(json_cache)

        if vif_id is not None:
            vif_list = [vif for vif in vifs if vif['id'] == vif_id]
            if not vif_list:
                # NOTE(jkoelker) The vif isn't in the cache, raise
                #                ValueError (probably inappropriatly)
                #                to trigger direct network_api lookup
                raise ValueError
            return vif_list[0]
        return vifs

    def index(self, req, server_id):
        """Returns the list of VIFs for a given instance."""
        context = req.environ['nova.context']
        entity_maker = _translate_vif_summary_view

        try:
            vifs = self._cached_items(context, server_id)
        except (ValueError, KeyError, AttributeError):
            # NOTE(jkoelker): If the json load (ValueError) or the
            #                 sqlalchemy FK (KeyError, AttributeError)
            #                 fail fall back to calling out the the
            #                 network api
            vifs = self._items(context, server_id)

        limited_list = common.limited(vifs, req)
        res = [entity_maker(vif) for vif in limited_list]
        return {'virtual_interfaces': res}

    def show(self, req, server_id, id):
        """Returns a single VIFs"""
        context = req.environ['nova.context']
        try:
            vif = self._cached_items(context, server_id, id)
        except (ValueError, KeyError, AttributeError):
            vif = self.network_api.get_vif(context, id)
        return _translate_vif_summary_view(vif)

    def update(self, req, server_id, id, body):
        """Update a VIF. This is not supported."""
        raise exc.HTTPBadRequest()

    def create(self, req, server_id, body):
        """Create a vif and attach it to the server"""
        if not body:
            raise exc.HTTPUnprocessableEntity()

        network_id = body.get('network_id')
        if network_id is None:
            raise exc.HTTPUnprocessableEntity()

        context = req.environ['nova.context']

        msg = _("Creating new vif on network %(network_id)s for instance"
                " %(server_id)s") % {'network_id': network_id,
                                    'server_id': server_id}
        LOG.audit(msg, context=context)

        vif = self.network_api.add_vif(context, server_id, network_id)
        return _translate_vif_summary_view(vif)

    def delete(self, req, server_id, id):
        """Remove the vif, unassociating it from its ips if any"""
        context = req.environ['nova.context']

        msg = _("Deleting vif %(vif_uuid)s from instance"
                " %(server_id)s") % {'vif_uuid': id,
                                    'server_id': server_id}
        LOG.audit(msg, context=context)

        self.network_api.remove_vif(context, id)
        return webob.Response(status_int=202)


class Virtual_interfaces(extensions.ExtensionDescriptor):
    """Virtual interface support"""

    name = "VirtualInterfaces"
    alias = "virtual_interfaces"
    namespace = "http://docs.openstack.org/ext/virtual_interfaces/api/v1.1"
    updated = "2011-10-28T00:00:00+00:00"

    def get_resources(self):
        metadata = _get_metadata()
        body_serializers = {
            'application/xml': wsgi.XMLDictSerializer(metadata=metadata,
                                                      xmlns=wsgi.XMLNS_V11)}
        serializer = wsgi.ResponseSerializer(body_serializers, None)
        controller = ServerVirtualInterfaceController()
        parent = dict(member_name='server',
                      collection_name='servers')

        collections = ('os-virtual-interfaces',)
        return [extensions.ResourceExtension(collection,
                                             controller=controller,
                                             parent=parent,
                                             serializer=serializer)
                for collection in collections]
