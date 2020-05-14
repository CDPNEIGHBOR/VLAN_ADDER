from nornir import InitNornir
from nornir.plugins.tasks.data import load_yaml
from nornir.plugins.tasks.text import template_file
from nornir.plugins.tasks.networking import netmiko_send_config, netmiko_send_command
from nornir.plugins.functions.text import print_result, print_title
from nornir.core.filter import F
from colorama import Fore, Style
import itertools as it
import threading
import time
import os


#DEFNINING NAME FOR THREADING 'LOCK' METHOD#
LOCK = threading.Lock()


def send_vlans(task):
    #CLEARS THE SCREEN AT START OF SCRIPT#
    os.system("clear")
    #ACQUIRES LOCK TO ALLOW USER INPUT TO BE OBTAINED WITHOUT SCRIPT BEING EXECUTED ON ONE HOST BEFORE THE OTHER#
    LOCK.acquire()
    #PRESENTS USER INPUT DIALOGUE ASKING FOR VLAN ID(S) and NAME(S) OF VLANS TO BE ADDED. REMOVES WHITE SPACE.
    new_vlan = input(Fore.GREEN + 'Please confirm the vlan you would like to add to ' + str(
        task.host) + ' :' + Style.RESET_ALL).replace(', ', ',')
    vlan_name = input('please give a name for these VLANS on ' + str(task.host) + ':').replace(', ', ',')
    LOCK.release()
    #IF STATEMENT ESTABLISHES IF MULTIPLE VLANS ARE TO BE ADDED BY CHECKING FOR PRESENCE OF COMMA IN INPUTS#
    #IF COMMAS ARE PRESENT, THE INPUT IS SPLIT AT THE COMMA, RESULTING IN A LIST STORED IN VARIABLES 'VLANS'
    # AND 'NAMES', OTHERWISE THE IMPUT IS SPLIT AT THE WHITESPACE#
    if ',' in new_vlan:
        vlans = new_vlan.split(',')
    else:
        vlans = new_vlan.split()
    if ',' in vlan_name:
        names = vlan_name.split(',')
    else:
        names = vlan_name.split()
    #CREATES A VARIBLE NAMED PAIRINGS BY EXECUTING THE TUPLE FUNCTION ON THE RESULT OF RUNNING ZIP_LONGEST OVER THE
    #'VLANS' AND 'NAMES' LISTS
    pairings = tuple(it.zip_longest(vlans, names))
    #LOADS CONTENT OF YAML FILE WHICH CONTAINS HOST SPECIFIC INFORMATION
    yaml_configs = task.run(task=load_yaml, file=f'./{task.host}.yaml')
    #STORES RESULT OF YAML_CONFIGS TASK IN HOST VARIABLE
    task.host['vars'] = yaml_configs.result
    #USES NETMIKO PLUGIN TO RUN 'SHOW VLAN' ON HOST TO OBTAIN CURRENT VLANS,
    #GENIE PARSER USED TO RETURN STRUCTURED DATA.
    current_vlans = task.run(task=netmiko_send_command, name='getting VLAN information',
                             command_string='show vlan', use_genie=True)
    #STORES RESULTS OF CURRENT_VLANS TASK IN VARIABLE NAMED 'EXISTING_VLANS'
    existing_vlans = current_vlans.result
    #EXISTING_VLANS VARIABLE IS A DICTIONARY, THE REQUIRED INFORMATION IS UNDER THE ['VLANS'] KEY. THIS PIECE OF CODE
    #ACCESSES THAT KEY AND STORES THE VALUE AS A HOST VARIABLE. THIS WILL BE USED TO ESTABLISH IF VLANS GIVEN AT START
    #OF SCRIPT ARE ALREADY PRESENT ON THE DEVICE.
    task.host['vars']['current_vlans'] = existing_vlans['vlans']
    #STORES VLAN/NAME PAIRS (TUPLE) IN HOST VARIABLE
    task.host['vars']['pairings'] = pairings
    LOCK.acquire()
    #CREATES AN EMPTY LIST THAT WILL STORE THE VLANS WHICH ARE TO ACTUALLY BE SENT TO THE DEVICE AFTER COMPARISON TO
    #EXISITING VLANS
    vlans_to_send = []
    #CREATE A LOOP TO ITERATE OVER THE PAIRS TUPLE
    for pair in pairings:
        #FOR EACH ENTRY IN THE TUPLE (PAIR) THE FIRST ELEMENT IS THE VLAN NUMBER ENTERED AT THE START OF THE SCRIPT
        #FOR EACH ITERATION OF THE LOOP, THIS ELEMENTS VALUE IS ASSIGNED TO THE VARIABLE NAMED 'VLAN'
        vlan = pair[0]
        #THE CONTENT OF THAT VARIABLE (A VLAN ID) IS COMPARED TO EXISTING VLANS ON DEVICE
        if vlan in existing_vlans['vlans']:
            #IF THE VLAN IN QUESTION IS PRESENT ON THE DEVICE ALREADY THE USER IS ASKED WETHER THEY WISH TO
            # OVERWRITE IT.
            confirm = input(Fore.RED + 'VLAN ' + vlan + ' ALREADY PRESENT ON ' + str(task.host) +
                            ' OVERWRITE?' + Style.RESET_ALL)
            confirm_cased = confirm.upper()
            #IF USER CHOOSES YES, THE VLAN/NAME PAIR IS ADDED TO THE VLANS_TO_SEND LIST CREATED EARLIER
            if confirm_cased == 'Y':
                vlans_to_send.append(pair)
            #IF THE USER CHOOSES NOT TO OVERWRITE, THE 'VLANS_TO_SEND' LIST REMAINS THE SAME
            elif confirm_cased == 'N':
                continue
        #IF THE VLAN IN QUESTION IS NOT ALREADY PRESENT ON THE DEVICE THE CORRESPONDING PAIR IS ADDED DIRECTLY
        #TO THE 'VLANS_TO_SEND' LIST VARIABLE.
        else:
            vlans_to_send.append(pair)
    #CREATE FINALISED SET OF VLAN ID/NAME PAIRS AND STORE THEM AS A TUPLE FOR RENDERING WITH JINJA LATER.
    final_pairs = tuple(vlans_to_send)
    task.host['vars']['pairings'] = final_pairs
    vlan_list = []
    for pair in final_pairs:
        vlan_list.append(pair[0])
    task.host['vars']['vlans'] = vlan_list
    #PRINT DETAILS OF VLAN ID/NAME PAIRS TO BE SENT
    print(Fore.GREEN + ' THE FOLLOWING VLAN/NAME PAIRS WILL BE SENT TO ' + str(task.host) + ' ' + str(
        final_pairs) + Style.RESET_ALL)
    LOCK.release()
    #NORNIR TASK TO RENDER JINJA2 TEMPLATE WITH HOST VARIABLES
    render = task.run(task=template_file, template='trunk.j2', path='./templates')
    #STORES THE RESULTING RENDERED TEMPLATE IN A HOST VARIABLE
    task.host['config'] = render.result
    #TAKES CONTENTS OF HOST VARIABLE CONTAINING JINJA TEMPLATE AND SPLITS IT INTO SEPERATE LINES TO BE SENT WITH
    #NORNIR
    send_to_device = task.host['config']
    commands = send_to_device.splitlines()
    #SEND RENDERED TEMPLATE TO HOST WITH NORNIR.
    task.run(task=netmiko_send_config, name="Sending configs to device", config_commands=commands)


def main():
    # INITIALISING NORNIR#
    nr = InitNornir(config_file='config.yaml')
    # SETTING FILTER CONTEXT#
    gc_targets = nr.filter(F(groups__contains='glasgownet') & F(groups__contains='core'))
    result = gc_targets.run(task=send_vlans)
    print_result(result)


if __name__ == '__main__':
    main()
