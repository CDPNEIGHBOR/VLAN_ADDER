#!/usr/bin/env python3

from nornir import InitNornir
from nornir.plugins.tasks.data import load_yaml
from nornir.plugins.tasks.text import template_file
from nornir.plugins.tasks.networking import netmiko_send_config, netmiko_send_command
from nornir.plugins.functions.text import print_result, print_title
from nornir.core.filter import F
from colorama import Fore, Style
import itertools as it
import threading
import logging
import os

LOCK = threading.Lock()


def get_input(task):
    os.system("clear")
    LOCK.acquire()
    new_vlan = input(Fore.GREEN + 'Please confirm the vlan you would like to add to ' + str(
        task.host) + ' :' + Style.RESET_ALL).replace(', ', ',')
    vlan_name = input('please give a name for these VLANS on ' + str(task.host) + ':').replace(', ', ',')
    LOCK.release()
    if ',' in new_vlan:
        vlans = new_vlan.split(',')
    else:
        vlans = new_vlan.split()
    if ',' in vlan_name:
        names = vlan_name.split(',')
    else:
        names = vlan_name.split()
    pairings = tuple(it.zip_longest(vlans, names))
    task.run(task=get_current, pairings=pairings)


def get_current(task, pairings):
    yaml_configs = task.run(task=load_yaml, file=f'./{task.host}.yaml')
    task.host['vars'] = yaml_configs.result
    current_vlans = task.run(task=netmiko_send_command, name='getting VLAN information',
                             command_string='show vlan', use_genie=True)
    existing_vlans = current_vlans.result
    task.host['vars']['current_vlans'] = existing_vlans['vlans']
    task.host['vars']['pairings'] = pairings
    LOCK.acquire()
    vlans_to_send = []
    for pair in pairings:
        vlan = pair[0]
        if vlan in existing_vlans['vlans']:
            confirm = input(Fore.RED + 'VLAN ' + vlan + ' ALREADY PRESENT ON ' + str(task.host) +
                            ' OVERWRITE?' + Style.RESET_ALL)
            confirm_cased = confirm.upper()
            if confirm_cased == 'Y':
                vlans_to_send.append(pair)
            elif confirm_cased == 'N':
                continue
        else:
            vlans_to_send.append(pair)
    final_pairs = tuple(vlans_to_send)
    task.host['vars']['pairings'] = final_pairs
    vlan_list = []
    for pair in final_pairs:
        vlan_list.append(pair[0])
    task.host['vars']['vlans'] = vlan_list
    print(Fore.GREEN + ' THE FOLLOWING VLAN/NAME PAIRS WILL BE SENT TO ' + str(task.host) + ' ' + str(
        final_pairs) + Style.RESET_ALL)
    LOCK.release()
    task.run(task=send_vlans)


def send_vlans(task):
    render = task.run(task=template_file, template='trunk.j2', path='./templates')
    task.host['config'] = render.result
    send_to_device = task.host['config']
    commands = send_to_device.splitlines()
    task.run(task=netmiko_send_config, name="Sending configs to device", severity_level=logging.WARNING,
             config_commands=commands)


def main():
    nr = InitNornir(config_file='config.yaml')
    gc_targets = nr.filter(F(groups__contains='glasgownet') & F(groups__contains='core'))
    result = gc_targets.run(task=get_input)
    print_result(result, severity_level=logging.WARNING)


if __name__ == '__main__':
    main()
