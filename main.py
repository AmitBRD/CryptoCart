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
ws_channel="582e88e0-d413-454e-977d-4d43a5066918"
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
            "value":"https://blockset.com/webhooks/582e88e0-d413-454e-977d-4d43a5066918"},
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
  print(message)
  # address = self.get_argument("address")
  # global monitor_address
  # print(monitor_address)
  # if(address in monitor_address):
  #   monitor_address.remove(address)
  #   self.finish(json.dumps(address))
  # else:
  #   self.finish("NO SUCH CART")

@gen.coroutine
def ping_socket(socket):
    while True:
      socket.write_message('{"type":"ping"}')
      yield gen.sleep(1)

@gen.coroutine
def connect_ws():
   subscription_socket = yield websocket_connect(websocket_url,ping_interval=5, on_message_callback=monitor_ws)
   subscription_socket.write_message('{"type":"listen","payload":{"channel":"'+ws_channel+'"}}')
   subscription_socket.write_message('{"type":"catch-up","payload":{"channel":"'+ws_channel+'"}}')
   ioloop.IOLoop.instance().spawn_callback(ping_socket,subscription_socket)
   print('connected to channel:'+ws_channel)

if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    
   
    # task = tornado.ioloop.PeriodicCallback(
    #         lambda: print('period'),
    #         2000)   # 2000 ms
    # task.start()
    connect_ws()
    ioloop.IOLoop.instance().spawn_callback(monitor_for_transfers)
    tornado.ioloop.IOLoop.current().start()
