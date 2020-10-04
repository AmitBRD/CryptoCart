import tornado
from tornado import (
  concurrent,
  gen,
  httpserver,
  ioloop,
  log,
  process,
  web
)
import asyncio
from pool import Pool
from threading import Condition
import os
from walletkit import BRSequence
from queue import Queue,Empty
import binascii


NUM_BASKETS = 5
br_sequence = BRSequence()
baskets = Queue(NUM_BASKETS)
monitor_address = set()

#Dont put that here
phrase = "ginger settle marine tissue robot crane night number ramp coast roast critic".encode("UTF-8")


for i in range(NUM_BASKETS):
  seed = [0] * 64
  key = br_sequence.derive_private_key_from_seed_and_index_eth(seed,phrase,i)
  address = br_sequence.generate_address_eth(key["pubKey"], key["compressed"])
  baskets.put(address)

pool = Pool(baskets)


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
      try:
          with pool.lease() as address:
            addr_str = str(binascii.hexlify(bytearray(address["bytes"])))
            print('write address stream')
            yield self.write("Use address:"+addr_str)
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
    monitor_address.remove(address) 
    self.finish(str("unlocking"+address))
    

def make_app():
    print(os.getcwd())
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/static/(.*)", StaticHandler, {'path': os.getcwd()}),
        (r"/webhook",WebhookHandler)

    ])

if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    # task = tornado.ioloop.PeriodicCallback(
    #         lambda: print('period'),
    #         2000)   # 2000 ms
    # task.start()
    ioloop.IOLoop.instance().spawn_callback(monitor_for_transfers)
    tornado.ioloop.IOLoop.current().start()