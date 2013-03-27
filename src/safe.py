""" Implementation of pol safes.  See `Safe`. """

import time
import struct
import logging
import binascii
import multiprocessing

import pol.elgamal
import pol.ks
import pol.hash

import msgpack
import gmpy

# TODO Generating random numbers seems CPU-bound.  Does the default random
#      generator wait for a certain amount of entropy?
import Crypto.Random
import Crypto.Random.random as random

l = logging.getLogger(__name__)

# Constants used for access slices
AS_MAGIC = binascii.unhexlify('1a1a8ad7')  # starting bytes of an access slice
AS_FULL = 0         # the access slice gives full access
AS_LIST = 1         # the access slice gives list-only access
AS_APPEND = 2       # the access slice gives append-only access

# We derive multiple keys from one base key using hashing and
# constants. For instance, given a base key K, the ElGamal private
# key for of the n-th block is Hash(K, KC_ELGAMAL, n)
KC_ELGAMAL = binascii.unhexlify('d53d376a7db498956d7d7f5e570509d5')
KC_LIST = binascii.unhexlify('d53d376a7db498956d7d7f5e570509d5')
KC_APPEND = binascii.unhexlify('76001c344cbd9e73a6b5bd48b67266d9')

class SafeFormatError(ValueError):
    pass

class Safe(object):
    """ A pol safe deniably stores containers. (Containers store secrets.) """

    def __init__(self, data):
        self.data = data
        if 'key-stretching' not in self.data:
            raise SafeFormatError("Missing `key-stretching' attribute")
        if 'hash' not in self.data:
            raise SafeFormatError("Missing `hash' attribute")
        self.ks = pol.ks.KeyStretching.setup(self.data['key-stretching'])
        self.hash = pol.hash.Hash.setup(self.data['hash'])

    def store(self, stream):
        start_time = time.time()
        l.info('Packing ...')
        msgpack.pack(self.data, stream)
        l.info(' packed in %.2fs', time.time() - start_time)

    def open(self, password):
        pass

    @staticmethod
    def load(stream):
        start_time = time.time()
        l.info('Unpacking ...')
        data = msgpack.unpack(stream, use_list=True)
        l.info(' unpacked in %.2fs', time.time() - start_time)
        if ('type' not in data or not isinstance(data['type'], basestring)
                or data['type'] not in TYPE_MAP):
            raise SafeFormatError("Invalid `type' attribute")
        return TYPE_MAP[data['type']](data)

    @staticmethod
    def generate(typ='elgamal', *args, **kwargs):
        if typ not in TYPE_MAP:
            raise ValueError("I do not know Safe type %s" % typ)
        return TYPE_MAP[typ].generate(*args, **kwargs)

class ElGamalSafe(Safe):
    """ Default implementation using rerandomization of ElGamal. """

    def __init__(self, data):
        super(ElGamalSafe, self).__init__(data)
        # Check if `data' makes sense.
        for attr in ('group-params', 'n-blocks', 'blocks', 'block-index-size'):
            if not attr in data:
                raise SafeFormatError("Missing attr `%s'" % attr)
        for attr, _type in {'blocks': list,
                            'group-params': list,
                            'block-index-size': int,
                            'n-blocks': int}.iteritems():
            if not isinstance(data[attr], _type):
                raise SafeFormatError("`%s' should be a `%s'" % (attr, _type))
        if not len(data['blocks']) == data['n-blocks']:
            raise SafeFormatError("Amount of blocks isn't `n-blocks'")
        if not len(data['group-params']) == 2:
            raise SafeFormatError("`group-params' should contain 2 elements")
        # TODO Should we check whether the group parameters are safe?
        for x in data['group-params']:
            if not isinstance(x, basestring):
                raise SafeFormatError("`group-params' should contain strings")
        if data['block-index-size'] == 1:
            self._block_index_struct = struct.Struct('>B')
        elif data['block-index-size'] == 4:
            self._block_index_struct = struct.Struct('>H')
        elif data['block-index-size'] == 4:
            self._block_index_struct = struct.Struct('>I')
    @staticmethod
    def generate(n_blocks=1024, block_index_size=2, ks=None, _hash=None,
                    gp_bits=1024, precomputed_gp=False,
                    nthreads=None, progress=None):
        """ Creates a new safe. """
        if precomputed_gp:
            gp = pol.elgamal.precomputed_group_params(gp_bits)
        else:
            gp = pol.elgamal.generate_group_params(bits=gp_bits,
                                    nthreads=nthreads, progress=progress)
        if ks is None:
            ks = pol.ks.KeyStretching.setup()
        if _hash is None:
            _hash = pol.hash.Hash.setup()
        safe = Safe(
                {'type': 'elgamal',
                 'n-blocks': n_blocks,
                 'block-index-size': block_index_size,
                 'group-params': [x.binary() for x in gp],
                 'key-stretching': ks.params,
                 'hash': _hash.params,
                 'blocks': [[
                    # FIXME stub
                    gmpy.mpz(random.randint(2, int(gp.p))).binary(),
                    gmpy.mpz(random.randint(2, int(gp.p))).binary(),
                    gmpy.mpz(random.randint(2, int(gp.p))).binary()
                            ]
                         for i in xrange(n_blocks)]})
        return safe

    @property
    def nblocks(self):
        """ Number of blocks. """
        return self.data['n-blocks']

    @property
    def block_index_size(self):
        """ Size of a block index. """
        return self.data['block-index-size']

    @property
    def group_params(self):
        """ The group parameters. """
        return pol.elgamal.group_parameters(
                    *[gmpy.mpz(x, 256) for x in self.data['group-params']])
    
    def rerandomize(self, nthreads=None):
        """ Rerandomizes blocks: they will still decrypt to the same
            plaintext. """
        if not nthreads:
            nthreads = multiprocessing.cpu_count()
        l.debug("Rerandomizing %s blocks on %s threads ...",
                    self.nblocks, nthreads)
        pool = multiprocessing.Pool(nthreads, Crypto.Random.atfork)
        start_time = time.time()
        gp = self.group_params
        self.data['blocks'] = pool.map(_eg_rerandomize_block,
                    [(gp.g, gp.p, b) for b in self.data['blocks']])
        secs = time.time() - start_time
        kbps = self.nblocks * gmpy.numdigits(gp.p,2) / 1024.0 / 8.0 / secs
        l.debug(" done in %.2fs; that is %.2f KB/s", secs, kbps)

    def _index_to_bytes(self, index):
        self._block_index_struct.pack(index)
    def _index_from_bytes(self, s):
        self._block_index_struct.unpack(s)

def _eg_rerandomize_block(g_p_block):
    """ Given [g, p, block], rerandomizes block using group
        parameters g and p """
    g, p, raw_b = g_p_block
    s = random.randint(2, int(p))
    b = [gmpy.mpz(raw_b[0], 256),
         gmpy.mpz(raw_b[1], 256),
         gmpy.mpz(raw_b[2], 256)]
    b[0] = (b[0] * pow(g, s, p)) % p
    b[1] = (b[1] * pow(b[2], s, p)) % p
    raw_b[0] = b[0].binary()
    raw_b[1] = b[1].binary()
    return raw_b

TYPE_MAP = {'elgamal': ElGamalSafe}
