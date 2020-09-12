#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2017, Gaudenz Steinlin <gaudenz.steinlin@cloudscale.ch>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = '''
---
module: floating_ip
short_description: Manages floating IPs on the cloudscale.ch IaaS service
description:
  - Create, assign and delete floating IPs on the cloudscale.ch IaaS service.
notes:
  - Idempotency depends on the C(ip) parameter.
  - Once a floating_ip is created, all parameters except C(server), C(reverse_ptr) and C(tags) are read-only.
  - This module requires the ipaddress python library. This library is included in Python since version 3.3. It is available as a
    module on PyPI for earlier versions.
author:
  - Gaudenz Steinlin (@gaudenz)
  - Denis Krienbühl (@href)
version_added: 1.0.0
options:
  state:
    description:
      - State of the floating IP.
    default: present
    choices: [ present, absent ]
    type: str
  ip:
    description:
      - Floating IP address to change.
      - Required to assign the IP to a different server or if I(state) is absent.
    aliases: [ network ]
    type: str
  ip_version:
    description:
      - IP protocol version of the floating IP.
    choices: [ 4, 6 ]
    type: int
  server:
    description:
      - UUID of the server assigned to this floating IP.
    type: str
  type:
    description:
      - The type of the floating IP.
    choices: [ regional, global ]
    type: str
    default: regional
  region:
    description:
      - Region in which the floating IP resides (e.g. C(lgp) or C(rma)).
        If omitted, the region of the project default zone is used.
        This parameter must be omitted if I(type) is set to C(global).
    type: str
  prefix_length:
    description:
      - Only valid if I(ip_version) is 6.
      - Prefix length for the IPv6 network. Currently only a prefix of /56 can be requested. If no I(prefix_length) is present, a
        single address is created.
    choices: [ 56 ]
    type: int
  reverse_ptr:
    description:
      - Reverse PTR entry for this address.
      - You cannot set a reverse PTR entry for IPv6 floating networks. Reverse PTR entries are only allowed for single addresses.
    type: str
  tags:
    description:
      - Tags associated with the floating IP. Set this to C({}) to clear any tags.
    type: dict
    version_added: 1.1.0
extends_documentation_fragment: cloudscale_ch.cloud.api_parameters
'''

EXAMPLES = '''
# Request a new floating IP without server assignment
- name: Request a floating IP
  cloudscale_ch.cloud.floating_ip:
    ip_version: 4
    api_token: xxxxxx

# Request a new floating IP
- name: Request a floating IP
  cloudscale_ch.cloud.floating_ip:
    ip_version: 4
    server: 47cec963-fcd2-482f-bdb6-24461b2d47b1
    reverse_ptr: my-server.example.com
    api_token: xxxxxx

# Assign an existing floating IP to a different server
- name: Move floating IP to backup server
  cloudscale_ch.cloud.floating_ip:
    ip: 192.0.2.123
    server: ea3b39a3-77a8-4d0b-881d-0bb00a1e7f48
    api_token: xxxxxx

# Request a new floating IPv6 network
- name: Request a floating IP
  cloudscale_ch.cloud.floating_ip:
    ip_version: 6
    prefix_length: 56
    server: 47cec963-fcd2-482f-bdb6-24461b2d47b1
    api_token: xxxxxx
    region: lpg1

# Assign an existing floating network to a different server
- name: Move floating IP to backup server
  cloudscale_ch.cloud.floating_ip:
    ip: '{{ floating_ip.network | ip }}'
    server: ea3b39a3-77a8-4d0b-881d-0bb00a1e7f48
    api_token: xxxxxx

# Release a floating IP
- name: Release floating IP
  cloudscale_ch.cloud.floating_ip:
    ip: 192.0.2.123
    state: absent
    api_token: xxxxxx
'''

RETURN = '''
href:
  description: The API URL to get details about this floating IP.
  returned: success when state == present
  type: str
  sample: https://api.cloudscale.ch/v1/floating-ips/2001:db8::cafe
network:
  description: The CIDR notation of the network that is routed to your server.
  returned: success when state == present
  type: str
  sample: 2001:db8::cafe/128
next_hop:
  description: Your floating IP is routed to this IP address.
  returned: success when state == present
  type: str
  sample: 2001:db8:dead:beef::42
reverse_ptr:
  description: The reverse pointer for this floating IP address.
  returned: success when state == present
  type: str
  sample: 185-98-122-176.cust.cloudscale.ch
server:
  description: The floating IP is routed to this server.
  returned: success when state == present
  type: str
  sample: 47cec963-fcd2-482f-bdb6-24461b2d47b1
ip:
  description: The floating IP address or network. This is always present and used to identify floating IPs after creation.
  returned: success
  type: str
  sample: 185.98.122.176
region:
  description: The region of the floating IP.
  returned: success when state == present
  type: dict
  sample: {'slug': 'lpg'}
state:
  description: The current status of the floating IP.
  returned: success
  type: str
  sample: present
tags:
  description: Tags assosiated with the floating IP.
  returned: success
  type: dict
  sample: { 'project': 'my project' }
  version_added: 1.1.0
'''

import traceback

IPADDRESS_IMP_ERR = None
try:
    from ipaddress import ip_network
    HAS_IPADDRESS = True
except ImportError:
    IPADDRESS_IMP_ERR = traceback.format_exc()
    HAS_IPADDRESS = False

from ansible.module_utils.basic import AnsibleModule, env_fallback, missing_required_lib
from ..module_utils.api import (
    AnsibleCloudscaleBase,
    cloudscale_argument_spec,
)


class AnsibleCloudscaleFloatingIP(AnsibleCloudscaleBase):

    def __init__(self, module):
        super(AnsibleCloudscaleFloatingIP, self).__init__(module)

        # Initialize info dict
        # Set state to absent, will be updated by self.update_info()
        self.info = {'state': 'absent'}

        if self._module.params['ip']:
            self.update_info()

    @staticmethod
    def _resp2info(resp):
        # If the API response has some content, the floating IP must exist
        resp['state'] = 'present'

        # Add the IP address to the response, otherwise handling get's to complicated as this
        # has to be converted from the network all the time.
        resp['ip'] = str(ip_network(resp['network']).network_address)

        # Replace the server with just the UUID, the href to the server is useless and just makes
        # things more complicated
        if resp['server'] is not None:
            resp['server'] = resp['server']['uuid']

        return resp

    def update_info(self):
        resp = self._get('floating-ips/' + self._module.params['ip'])
        if resp:
            self.info = self._resp2info(resp)
        else:
            self.info = {'ip': self._module.params['ip'],
                         'state': 'absent'}

    def request_floating_ip(self):
        params = self._module.params

        # check for required parameters to request a floating IP
        self._module.fail_on_missing_params(('ip_version',))

        data = {
            'ip_version': params['ip_version'],
            'server': params['server'],
            'prefix_length': params['prefix_length'],
            'reverse_ptr': params['reverse_ptr'],
            'type': params['type'],
            'region': params['region'],
            'tags': params['tags'],
        }

        self.info = self._resp2info(self._post('floating-ips', data))

    def release_floating_ip(self):
        self._delete('floating-ips/%s' % self._module.params['ip'])
        self.info = {'ip': self.info['ip'], 'state': 'absent'}

    def update_floating_ip(self):
        params = self._module.params

        if not params['server']:
            self._module.fail_json(msg='Missing required parameter to update a floating IP: server.')

        data = {
            'server': params['server'],
            'tags': params['tags'],
        }

        self.info = self._resp2info(self._post('floating-ips/%s' % params['ip'], data))


def main():
    argument_spec = cloudscale_argument_spec()
    argument_spec.update(dict(
        state=dict(default='present', choices=('present', 'absent'), type='str'),
        ip=dict(aliases=('network', ), type='str'),
        ip_version=dict(choices=(4, 6), type='int'),
        server=dict(type='str'),
        type=dict(type='str', choices=('regional', 'global'), default='regional'),
        region=dict(type='str'),
        prefix_length=dict(choices=(56,), type='int'),
        reverse_ptr=dict(type='str'),
        tags=dict(type='dict'),
    ))

    module = AnsibleModule(
        argument_spec=argument_spec,
        required_one_of=(('ip', 'ip_version'),),
        supports_check_mode=True,
    )

    if not HAS_IPADDRESS:
        module.fail_json(msg=missing_required_lib('ipaddress'), exception=IPADDRESS_IMP_ERR)

    target_state = module.params['state']
    target_server = module.params['server']
    floating_ip = AnsibleCloudscaleFloatingIP(module)
    current_state = floating_ip.info['state']
    current_server = floating_ip.info['server'] if 'server' in floating_ip.info else None

    if module.check_mode:
        module.exit_json(changed=not target_state == current_state or
                         (current_state == 'present' and current_server != target_server),
                         **floating_ip.info)

    changed = False
    if current_state == 'absent' and target_state == 'present':
        floating_ip.request_floating_ip()
        changed = True
    elif current_state == 'present' and target_state == 'absent':
        floating_ip.release_floating_ip()
        changed = True
    elif current_state == 'present' and current_server != target_server:
        floating_ip.update_floating_ip()
        changed = True

    module.exit_json(changed=changed, **floating_ip.info)


if __name__ == '__main__':
    main()
