from web3 import Web3
import json
import requests
import csv
from prettytable import PrettyTable

from dotenv import load_dotenv
from os import getenv

import asyncio

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style
from pygments.lexers.solidity import SolidityLexer
from prompt_toolkit import print_formatted_text, HTML
from halo import Halo
from time import sleep

@Halo(text='Sending DITTO Drops on BSC', spinner='dots')
def send_tx(receiver, amount, vars):
    acc = vars['w3b'].eth.account.from_key(vars['pk'])
    erc20_abi = json.load(open('erc20_abi.json', 'r'))
    erc20 = vars['w3b'].eth.contract(address=vars['ditto_erc20'], abi=erc20_abi)
    nonce = vars['w3b'].eth.getTransactionCount(acc.address)
    tx = erc20.functions.transfer(receiver, amount).buildTransaction({
        'chainId': vars['bsc_chain_id'],
        'gas': 200000,
        'gasPrice': vars['w3b'].toWei('20', 'gwei'),
        'nonce': nonce,
    })
    signed_txn = vars['w3b'].eth.account.sign_transaction(tx, private_key=vars['pk'])

    spinner = Halo(text='Sending Ditto Tokens to '+receiver, spinner='line')
    spinner.start()

    sent_tx = vars['w3b'].eth.sendRawTransaction(signed_txn.rawTransaction)

    # wait for deployment transaction to be mined
    while True:
        try:
            receipt = vars['w3b'].eth.getTransactionReceipt(sent_tx)
            if receipt:
                print("Ditto tokens sent to " + receiver);
                break
        except:
            sleep(1)
    spinner.stop()

def check_to_send(tx_list, latest_block, vars):
    while True:
        if(len(tx_list)>0):
            if (latest_block - int(tx_list[0][0]) >= vars['confirmations']):

                block = tx_list[0][0]

                receiver = tx_list[0][1]
                amount = tx_list[0][4]

                print("\nConfirmations reached.\n")
                print("RECEIVER {} AMOUNT {}".format(receiver,amount))

                #  event_filter = vars['swap_contract'].events.SwapDeposit.createFilter(fromBlock=block, toBlock=block)

                #  for event in event_filter.get_new_entries():
                #     depositor = e['args']['depositor']
                #     output_amount = e['args']['outputAmount']

                # if(depositor == receiver and output_amount == amount):

                send_tx(receiver, amount, vars)
                
                del tx_list[0]
            else:
                return
        else:
            return


def check_for_duplicates(tx_list, e):
    for t in tx_list:
        if (e['args']['depositor'] == t[1] and e['args']['outputAmount'] == t[4]):
            print("\nDouble inclusion detected\n");
            return True

    return False


def handle_event(e, tx_list, confirmations, latest_block):

    if (check_for_duplicates(tx_list, e)):
        return

    block_number = e['blockNumber']
    depositor = e['args']['depositor']
    input_token = e['args']['input']
    input_amount = e['args']['inputAmount']
    output_amount = e['args']['outputAmount']
    tx = [block_number, depositor, input_token, input_amount, output_amount]
    tx_list.append(tx)
    print("=====Pending Transfers====      "+"Current Block: " + str(latest_block))
    x  = PrettyTable()
    header = ['block', 'address', 'inputTokenName', 'inputAmount', 'outputAmount']
    x.field_names = header
    x.add_rows(tx_list)
    print(x)

async def log_loop(event_filter, poll_interval, tx_list, vars):
    while True:
        latest_block = vars['w3e'].eth.getBlock('latest')['number']
        if(len(tx_list)>0):
            check_to_send(tx_list, latest_block, vars)
        for event in event_filter.get_new_entries():
            handle_event(event, tx_list, vars['confirmations'], latest_block)
        await asyncio.sleep(poll_interval)

def real_time_swap_events(vars):
    #latest = vars['w3e'].eth.blockNumber 
    #print("LATEST: {}".format(latest))
    #filterblock = latest - vars['confirmations']
    event_filter = vars['swap_contract'].events.SwapDeposit.createFilter(fromBlock="latest")
    loop = asyncio.get_event_loop()
    tx_list = []
    try:
        loop.run_until_complete(
            asyncio.gather(log_loop(event_filter, 2, tx_list, vars)))
    finally:
        loop.close()

def print_deposit_events(swap_contract, fromBlock, toBlock):
    events = swap_contract.events.SwapDeposit.getLogs(fromBlock=fromBlock, toBlock=toBlock)
    f = open(str(fromBlock)+"-"+str(toBlock)+'.csv', 'w')
    writer = csv.writer(f)
    x  = PrettyTable()
    header = ['block', 'address', 'inputTokenName', 'inputAmount', 'outputAmount']
    writer.writerow(header)
    x.field_names = header
    for e in events:
        block_number = e['blockNumber']
        depositor = e['args']['depositor']
        input_token = e['args']['input']
        input_amount = e['args']['inputAmount']
        output_amount = e['args']['outputAmount']
        row = [block_number, depositor, input_token, input_amount, output_amount]
        writer.writerow(row)
        x.add_row(row)
    f.close()
    print(x)
    print_formatted_text(HTML("<aaa fg='ansiwhite' bg='ansigreen'>&#9989; Saved to "+str(fromBlock)+"-"+str(toBlock)+".csv</aaa>"))



def main():
    abi = json.load(open('abi.json', 'r'))

    #load env
    load_dotenv('.env')
    vars = {}
    vars['pk'] = getenv('pk')
    vars['infura_id'] = getenv('infura_id')
    vars['ditto_erc20'] = getenv('ditto_erc20')
    vars['swap_contract_address'] = getenv('swap_contract_address')
    vars['bsctestnet_rpc'] = getenv('bsctestnet_rpc')
    vars['bsc_rpc'] = getenv('bsc_rpc')
    vars['ethereum_chain'] = getenv('ethereum_chain')
    vars['bsc_chain'] = getenv('bsc_chain')
    vars['bsc_chain_id'] = int(getenv('bsc_chain_id'))
    vars['mainnet_rpc'] = getenv('mainnet_rpc')
    vars['ropsten_rpc'] = getenv('ropsten_rpc')
    vars['confirmations'] = int(getenv('confirmations'))

    #init web3

    #set ropsten or mainnet
    if vars['ethereum_chain'] == 'mainnet':
        w3e = Web3(Web3.HTTPProvider(vars['mainnet_rpc']+vars['infura_id']))
    else:
        w3e = Web3(Web3.HTTPProvider(vars['ropsten_rpc']+vars['infura_id']))
    vars['w3e'] = w3e
    if vars['bsc_chain'] == 'mainnet':
        w3b = Web3(Web3.HTTPProvider(vars['bsc_rpc']))
    else:
        w3b = Web3(Web3.HTTPProvider(vars['bsctestnet_rpc']))
    vars['w3b'] = w3b
    vars['swap_contract'] = w3e.eth.contract(address=vars['swap_contract_address'], abi=abi)
    #init prompt toolkit
    completer = WordCompleter(['historical swaps', 'real time swaps'])
    style = Style.from_dict({
        'completion-menu.completion': 'bg:#008888 #ffffff',
        'completion-menu.completion.current': 'bg:#00aaaa #000000',
        'scrollbar.background': 'bg:#88aaaa',
        'scrollbar.button': 'bg:#222222',
    })
    session = PromptSession(
        lexer=PygmentsLexer(SolidityLexer), completer=completer, style=style)

    while True:
        try:
            text = session.prompt('> ')
            print(text)
            if (text == 'historical swaps'):
                startBlock = session.prompt(HTML('> &#9658; Start Block: '))
                endBlock = session.prompt(HTML('> &#9658; End Block: '))
                print_deposit_events(vars['swap_contract'], int(startBlock), int(endBlock))
            elif (text == 'real time swaps'):
                real_time_swap_events(vars)

        except KeyboardInterrupt:
            continue  # Control-C pressed. Try again.
        except EOFError:
            break  # Control-D pressed.

if __name__ == '__main__':
    main()