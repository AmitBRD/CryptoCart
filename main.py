import tornado
from tornado import (
  concurrent,
  gen,
  httpserver,
  httpclient,
  ioloop,
  log,
  process,
  web
)

from tornado.httpclient import HTTPRequest
import asyncio
from pool import Pool
from threading import Condition
from tornado.websocket import websocket_connect
import os
from walletkit import BRSequence
from queue import Queue,Empty
import binascii
import json


NUM_BASKETS = 5
br_sequence = BRSequence()
baskets = Queue(NUM_BASKETS)
monitor_address = set()

http_client = httpclient.HTTPClient()
baseUrl = "https://api.blockset.com"
subscriptionsUrl = baseUrl + "/subscriptions"
websocket_url= "wss://blockset.com/webhooks/ws"
ws_channel="582e88e0-d413-454e-977d-4d43a5066917"
addresses = []

#Dont put that here
phrase = "ginger settle marine tissue robot crane night number ramp coast roast critic".encode("UTF-8")


for i in range(NUM_BASKETS):
  seed = [0] * 64
  #Eth Addresses cannot be generated with DER compressed 
  val = br_sequence.derive_private_key_from_seed_and_index_eth(seed,phrase,i,_der_compressed=0)
  address = br_sequence.generate_address_eth(val["pubKey"], val["compressed"])
  baskets.put(address)
  #print( bytearray(address["bytes"]).hex())
  addresses.append("0x"+bytearray(address["bytes"]).hex())


requestHeader = {"Content-Type": "application/json",
            "accept":"application/json",
            "authorization":"Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI0MTY2NjVlNC1hYjJjLTRmOTUtOWRjMy00MTAwNDBjNTRmNzUiLCJicmQ6Y3QiOiJjbGkiLCJleHAiOjkyMjMzNzIwMzY4NTQ3NzUsImlhdCI6MTYwNTE1NjM1M30.SFVAOUfbOj-_6OEvloYEfVyeZbkglgPIdMzQtKAhz-3y3HN73NAJB36b7h-yIArIQkUDYULt9YkRYzRRG3Pk1Q"}
requestBody = {"device_id":"cryptoCart3",
          "endpoint":{
            "environment":"production",
            "kind":"webhook",
            "value":"https://blockset.com/webhooks/"+ws_channel},
            "currencies":[{"addresses":addresses,
            "currency_id":"ethereum-mainnet:__native__",
            "events":[{"confirmations":[1,6],"name":"confirmed"}]}]}

try:
  response = http_client.fetch(HTTPRequest(subscriptionsUrl, 'POST',
               body=json.dumps(requestBody), headers=requestHeader, follow_redirects=False))
               # body=json.dumps(requestBody), follow_redirects=False))
  print(response.body)
except httpclient.HTTPError as e:
  # HTTPError is raised for non-200 responses; the response
  # can be found in e.response.
  print("Error: " + str(e))
except Exception as e:
  # Other errors are possible, such as IOError.
  print("Error: " + str(e))
http_client.close()

pool = Pool(baskets)

# @gen.coroutine # Is this needed?
# def create_subscriptions():
#     http_client = httpclient.HTTPClient()
# try:
#     response = http_client.fetch("http://www.google.com/")
#     print(response.body)
# except httpclient.HTTPError as e:
#     # HTTPError is raised for non-200 responses; the response
#     # can be found in e.response.
#     print("Error: " + str(e))
# except Exception as e:
#     # Other errors are possible, such as IOError.
#     print("Error: " + str(e))
#http_client.close()

@gen.coroutine
def monitor_for_transfers():
  while True:
    yield print('make http requests to see if in_flight_baskets received')
    #update all received transfers
    yield gen.sleep(5)

async def eternity():
    # Sleep for one hour
    await asyncio.sleep(3600)
    print('yay!')

@gen.coroutine
def await_transfer_complete(address):
  while address in monitor_address:
    yield gen.sleep(0.1)
  return True

class StaticHandler(tornado.web.StaticFileHandler):
    def parse_url_path(self, url_path):
        print ('url_path:'+url_path)
        if not url_path or url_path.endswith('/'):
            url_path = url_path + 'index.html'
        return url_path

class MainHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def get(self):
      amount=self.get_argument("amount", 0)
      try:
          with pool.lease() as address:
            #addr_str = str(binascii.hexlify(bytearray(address["bytes"])))
            print('write address stream')
            addr_str = bytearray(address["bytes"]).hex()
            yield self.write(json.dumps(addr_str))
            global monitor_address
            print(monitor_address)
            #TODO; setup the monitor here
            monitor_address.add(addr_str)
            yield self.finish()
            print('write to stream finshed now monitor for transfer completion')
            #asyncio.wait_for(eternity,None)
            yield await_transfer_complete(addr_str)
            print('received so unlock address')
      except Empty: # parent of IOError, OSError *and* WindowsError where available
        yield self.finish('NO MORE BASKETS available')

#TODO:This needs authentication to be called so malicious user cannot unlock carts
class WebhookHandler(tornado.web.RequestHandler):
  @gen.coroutine
  def get(self):
    address = self.get_argument("address")
    global monitor_address
    print(monitor_address)
    if(address in monitor_address):
      monitor_address.remove(address)
      self.finish(json.dumps(address))
    else:
      self.finish("NO SUCH CART")



def make_app():
    print(os.getcwd())
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {'path': os.getcwd()+"/static/"}),
        (r"/webhook",WebhookHandler)

    ])

@gen.coroutine
def monitor_ws(message):
  print("DEBUG:",message)
  address,currency_id,amount = parse_message(message)
  if(address != None):
    print("address:", address, "currency_id:",currency_id, "amount:", amount)
    address = address[2:]
    global monitor_address
    print(monitor_address)
    if(address in monitor_address):
      monitor_address.remove(address)
      print(json.dumps(address))
    else:
      print("NO SUCH CART")

@gen.coroutine
def ping_socket(socket):
    while True:
      socket.write_message('{"type":"ping"}')
      yield gen.sleep(1)


def parse_message(message_json):
  msg = json.loads(message_json)
  if(msg["type"]=="http"):
    #the basket
    address = msg['payload']['body']['_embedded']['transfers'][1]['to_address']
    #amount transferred
    currency_id = msg["payload"]["body"]["_embedded"]["transfers"][1]["amount"]["currency_id"]
    #amount transferred
    amount = msg["payload"]["body"]["_embedded"]["transfers"][1]["amount"]["amount"]
    return address,currency_id,amount
  else:
    return None,None,None


@gen.coroutine
def connect_ws():
   subscription_socket = yield websocket_connect(websocket_url,ping_interval=5, on_message_callback=monitor_ws)
   subscription_socket.write_message('{"type":"listen","payload":{"channel":"'+ws_channel+'"}}')
   subscription_socket.write_message('{"type":"catch-up","payload":{"channel":"'+ws_channel+'"}}')
   ioloop.IOLoop.instance().spawn_callback(ping_socket,subscription_socket)
   print('connected to channel:'+ws_channel)

if __name__ == "__main__":
    #parse_message(r'{"type":"http","payload":{"timestamp":1605162943.512,"uuid":"39363a58-ab31-4be4-ab4a-fa1884f0a3bd","method":"POST","url":"/582e88e0-d413-454e-977d-4d43a5066918","headers":{"host":"blockset.com","x-request-id":"70997810f7a51b4a3049350aaac44c87","x-real-ip":"64.225.39.56","x-forwarded-for":"64.225.39.56","x-forwarded-host":"blockset.com","x-forwarded-port":"443","x-forwarded-proto":"https","x-original-uri":"/webhooks/582e88e0-d413-454e-977d-4d43a5066918","x-scheme":"https","x-original-forwarded-for":"64.225.39.56","content-length":"2598","accept-encoding":"gzip","cf-ipcountry":"US","cf-ray":"5f0e3c0ccf522133-SJC","cf-visitor":"{\"scheme\":\"https\"}","accept":"text/plain, application/json, application/*+json, */*","authorization":"Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJodHRwczovL2Jsb2Nrc2V0LmNvbS93ZWJob29rcy81ODJlODhlMC1kNDEzLTQ1NGUtOTc3ZC00ZDQzYTUwNjY5MTgiLCJuYmYiOjE2MDUxNjI0ODAsImlzcyI6IkJsb2Nrc2V0IiwiZXhwIjoxNjA1MTYzNDQwLCJpYXQiOjE2MDUxNjI1NDB9.FBjGmqaoXOY0ESuog6nMGP5bdWsSx8pFgd6ifA0ZDWgNprZsIs8O3AMtKkmix6w6tdp7JlW-O8Xv77raHOBabg","content-type":"application/json","user-agent":"okhttp/4.3.0","cf-request-id":"065cc3dbfb00002133442b4000000001","cf-connecting-ip":"64.225.39.56","cdn-loop":"cloudflare"},"body":{"transaction_id":"ethereum-mainnet:0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d","identifier":"0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d","hash":"0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d","blockchain_id":"ethereum-mainnet","timestamp":"2020-11-12T06:34:29.000+00:00","_embedded":{"transfers":[{"transfer_id":"ethereum-mainnet:0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d:0","blockchain_id":"ethereum-mainnet","from_address":"0xae70c9c9a6344ed3b8c1227dc46c218f38adb41a","to_address":"__fee__","index":0,"transaction_id":"ethereum-mainnet:0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d","amount":{"currency_id":"ethereum-mainnet:__native__","amount":"4809000000000000"},"meta":{},"acknowledgements":1,"layers":{},"_links":{"self":{"href":"http://10.138.4.239:8080/transfers/ethereum-mainnet:0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d:0"},"transaction":{"href":"http://10.138.4.239:8080/transactions/ethereum-mainnet:0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d"}}},{"transfer_id":"ethereum-mainnet:0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d:1","blockchain_id":"ethereum-mainnet","from_address":"0xae70c9c9a6344ed3b8c1227dc46c218f38adb41a","to_address":"0x8fb4cb96f7c15f9c39b3854595733f728e1963bc","index":1,"transaction_id":"ethereum-mainnet:0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d","amount":{"currency_id":"ethereum-mainnet:__native__","amount":"216340000000000"},"meta":{},"acknowledgements":1,"layers":{},"_links":{"self":{"href":"http://10.138.4.239:8080/transfers/ethereum-mainnet:0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d:1"},"transaction":{"href":"http://10.138.4.239:8080/transactions/ethereum-mainnet:0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d"}}}]},"size":21000,"fee":{"currency_id":"ethereum-mainnet:__native__","amount":"4809000000000000"},"confirmations":4,"index":8,"block_hash":"0x7864ffad68b6b2073a6f800f44ed9dcdc8b5fdcf20ee790700ca7b43c4863f3d","block_height":11241236,"status":"confirmed","calls":[],"meta":{"gasLimit":"0x5208","gasPrice":"0x355176b200","gasUsed":"0x5208","input":"0x","nonce":"0x8"},"acknowledgements":1,"layers":{},"_links":{"self":{"href":"http://10.138.4.239:8080/transactions/ethereum-mainnet:0xba0698315b33e4549d02e2ba2622eb40d5dca42709d58a8a6146cc66b784f98d"},"block":{"href":"http://10.138.4.239:8080/blocks/ethereum-mainnet:0x7864ffad68b6b2073a6f800f44ed9dcdc8b5fdcf20ee790700ca7b43c4863f3d"}}}}}')

    app = make_app()
    app.listen(8888)
    
   
    # task = tornado.ioloop.PeriodicCallback(
    #         lambda: print('period'),
    #         2000)   # 2000 ms
    # task.start()
    connect_ws()
    ioloop.IOLoop.instance().spawn_callback(monitor_for_transfers)
    tornado.ioloop.IOLoop.current().start()
