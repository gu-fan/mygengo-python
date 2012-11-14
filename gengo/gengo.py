#!/usr/bin/python
# All code provided from the http://gengo.com site, such as API example code
# and libraries, is provided under the New BSD license unless otherwise
# noted. Details are below.
#
# New BSD License
# Copyright (c) 2009-2012, myGengo, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# Neither the name of myGengo, Inc. nor the names of its contributors may
# be used to endorse or promote products derived from this software
# without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Official Python library for interfacing with the Gengo API.
"""

__author__ = 'Shawn Smith <shawn.smith@gengo.com>'
__version__ = '1.3.4'

import re
import hmac
import requests

from hashlib import sha1
from urllib import urlencode, quote
from time import time
from operator import itemgetter
from string import lower

# mockdb is a file with a dictionary of every API endpoint for Gengo.
from mockdb import api_urls, apihash

# There are some special setups (like a Django application) where
# simplejson exists. Past Python 2.6, this should never
# cause any problems.
try:
    # Python 2.6 and up
    import json
    json  # silence pyflakes
except ImportError:
    try:
        # Python 2.6 and below (2.4/2.5, 2.3 is not guranteed to work with
        # this library to begin with)
        import simplejson as json
        json  # silence pyflakes
    except ImportError:
        try:
            # This case gets rarer by the day, but if we need to, we can
            # pull it from Django provided it's there.
            from django.utils import simplejson as json
            json  # silence pyflakes
        except:
            raise Exception("gengo requires the simplejson library (or " +
                            "Python 2.6+) to work. " +
                            "http://www.undefined.org/python/")


class GengoError(Exception):
    """
    Generic error class, catch-all for most Gengo issues.
    Special cases are handled by APILimit and AuthError.

    Note: You need to explicitly import them into your code, e.g:

    from gengo import GengoError, GengoAuthError
    """
    def __init__(self, msg, error_code=None):
        self.msg = msg
        if error_code == 1000:
            # Auth errors tend to be the most requested for their own
            # Exception instances, so give it to the masses, yo.
            raise GengoAuthError(msg)

    def __str__(self):
        return repr(self.msg)


class GengoAuthError(GengoError):
    """
    Raised when you try to access a protected resource and it fails due
    to some issue with your authentication.
    """
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


class Gengo(object):
    def __init__(self, public_key=None, private_key=None, sandbox=False,
                 api_version='2', headers=None, debug=False):
        """
        Gengo(public_key = None, private_key = None, sandbox = False,
        headers = None)

        Instantiates an instance of Gengo.

        Parameters:
        public_key - Your 'public' key for Gengo. Retrieve this from your
        account information if you want to do authenticated calls.
        private_key - Your 'private' key for Gengo. Retrieve this from your
        account information if you want to do authenticated calls.
        sandbox - Whether to use the Gengo sandbox or not. Check with Gengo
        for the differences with this as it may change.
        api_version - version 2 and 1.1 are supported. defaults to 2
        headers - User agent header, dictionary style ala {'User-Agent':
        'Bert'}
        debug - a flag (True/False) which will cause the library to print
        useful debugging info.
        """
        self.api_url = \
            api_urls['sandbox'] if sandbox is True else api_urls['base']
        self.api_version = str(api_version)
        if self.api_version not in ('1.1', '2'):
            raise Exception("gengo-python library only supports " +
                            " versions 1.1 and 2 at the moment, please " +
                            " keep api_version to 1.1 or 2")
        self.public_key = public_key
        self.private_key = private_key
        self.headers = headers
        if self.headers is None:
            self.headers = \
                {'User-agent': 'Gengo Python Library;' +
                    'Version %s; http://gengo.com/' % __version__}
        self.headers['Accept'] = 'application/json'
        self.debug = debug

    def __getattr__(self, api_call):
        """
        The most magically awesome block of code you'll ever see.

        Rather than list out 9 million methods for this API, we just
        keep a table (see above) of every API endpoint and their
        corresponding function id for this library. This pretty much
        gives unlimited flexibility in API support - there's a slight
        chance of a performance hit here, but if this is
        going to be your bottleneck... well, don't use Python. ;P

        For those who don't get what's going on here, Python classes
        have this great feature known as __getattr__().
        It's called when an attribute that was called on an object
        doesn't seem to exist - since it doesn't exist,
        we can take over and find the API method in our table. We then
        return a function that downloads and parses
        what we're looking for, based on the key/values passed in.

        I'll hate myself for saying this, but this is heavily inspired
        by Ruby's "method_missing".

        Note: I'm largely borrowing this technique from another API
        library/wrapper I've written in the past (Twython).
        If you happen to read both sources and find the same text...
        well, that's why. ;)
        """
        def get(self, **kwargs):
            # Grab the (hopefully) existing method 'definition' to fire off
            # from our api hash table.
            fn = apihash[api_call]

            # Do a check here for specific job sets - we need to support
            # posting multiple jobs
            # at once, so see if there's an dictionary of jobs passed in,
            # pop it out, let things go on as normal,
            # then pick this chain back up below...
            post_data = {}
            if 'job' in kwargs:
                post_data['job'] = {'job': kwargs.pop('job')}
            if 'jobs' in kwargs:
                post_data['jobs'] = kwargs.pop('jobs')
            if 'comment' in kwargs:
                post_data['comment'] = kwargs.pop('comment')
            if 'action' in kwargs:
                post_data['action'] = kwargs.pop('action')
            if 'job_ids' in kwargs:
                post_data['job_ids'] = kwargs.pop('job_ids')

            # Set up a true base URL, abstracting away the need to care
            # about the sandbox mode
            # or API versioning at this stage.
            base_url = self.api_url.replace('{{version}}',
                                            'v%s' % self.api_version)

            # Go through and replace any mustaches that are in our API url
            # with their appropriate key/value pairs...
            # NOTE: We pop() here because we don't want the extra data
            # included and messing up our hash down the road.
            base = re.sub(
                '\{\{(?P<m>[a-zA-Z_]+)\}\}',
                lambda m: "%s" % kwargs.pop(m.group(1),
                                            # In case of debugging needs
                                            'no_argument_specified'),
                base_url + fn['url']
            )

            # Build up a proper 'authenticated' url...
            #
            # Note: for further information on what's going on here, it's
            # best to familiarize yourself  with the Gengo authentication
            # API. (http://gengo.com/services/api/dev-docs/authentication)
            query_params = dict([k, quote(str(v).encode('utf-8'))] for k, v
                                in kwargs.items())
            if self.public_key is not None:
                query_params['api_key'] = self.public_key
            query_params['ts'] = str(int(time()))

            # check whether the endpoint supports file uploads and check the
            # params for file_path and modify the query_params accordingly
            # needs to be refactored to a more general handling once we
            # also want to support ie glossary upload. for now it's tied to
            # jobs payloads
            if 'upload' in fn:
                file_data = {}
                for k, j in post_data['jobs']['jobs'].iteritems():
                    if j['type'] == 'file' and 'file_path' in j:
                        file_data['file_' + k] = open(j['file_path'], 'rb')
                        j['file_key'] = 'file_' + k
                        del j['file_path']
            else:
                file_data = False

            # If any further APIs require their own special signing needs,
            # fork here...
            # For now, we are supporting 1.1 only, but 2 is desired at some
            # point.
            # resp, content = self.signAndRequestAPILatest(fn, base,
            # query_params, post_data)
            # results = json.loads(content)
            response = self.signAndRequestAPILatest(fn, base, query_params,
                                                    post_data, file_data)
            results = response.json

            # See if we got any errors back that we can cleanly raise on
            if 'opstat' in results and results['opstat'] != 'ok':
                # In cases of multiple errors, the keys for results['err']
                # will be the job IDs.
                if not 'msg' and 'code' in results['err']:
                    concatted_msg = ''
                    for job_key, msg_code_list in results['err'].iteritems():
                        concatted_msg += '<%s: %s> ' % \
                            (job_key, msg_code_list[0]['msg'])
                    raise GengoError(concatted_msg,
                                     results['err'].itervalues().
                                     next()[0]['code'])
                raise GengoError(results['err']['msg'],
                                 results['err']['code'])

            # If not, return the results
            return results

        if api_call in apihash:
            return get.__get__(self)
        else:
            raise AttributeError

    def signAndRequestAPILatest(self, fn, base, query_params, post_data={},
                                file_data=False):
        """
        Request signatures between API v1 and later versions of the API
        differ greatly in how they're done, so they're kept in separate
        methods for now.

        This method signs the request with just the timestamp and
        private key, which is what api v1.1 relies on.

        fn - object mapping from mockdb describing POST, etc.
        base - Base URL to ping.
        query_params - Dictionary of data eventually getting sent over
        to Gengo.
        post_data - Any extra special post data to get sent over.
        """
        # Encoding jobs becomes a bit different than any other method call,
        # so we catch them and do a little
        # JSON-dumping action. Catching them also allows us to provide some
        # sense of portability between the various
        # job-posting methods in that they can all safely rely on passing
        # dictionaries around. Huzzah!
        req_method = requests.__getattribute__(lower(fn['method']))
        if fn['method'] == 'POST' or fn['method'] == 'PUT':
            if 'job' in post_data:
                query_params['data'] = json.dumps(post_data['job'],
                                                  separators=(',', ':'))
            elif 'jobs' in post_data:
                query_params['data'] = json.dumps(post_data['jobs'],
                                                  separators=(',', ':'))
            elif 'comment' in post_data:
                query_params['data'] = json.dumps(post_data['comment'],
                                                  separators=(',', ':'))
            elif 'action' in post_data:
                query_params['data'] = json.dumps(post_data['action'],
                                                  separators=(',', ':'))

            query_hmac = hmac.new(self.private_key,
                                  query_params['ts'],
                                  sha1)
            query_params['api_sig'] = query_hmac.hexdigest()

            if self.debug is True:
                print query_params

            if not file_data:
                return req_method(base,
                                  headers=self.headers,
                                  data=query_params)
            else:
                return req_method(base,
                                  headers=self.headers,
                                  files=file_data,
                                  data=query_params)
        else:
            query_string = urlencode(sorted(query_params.items(),
                                            key=itemgetter(0)))
            if self.private_key is not None:
                query_hmac = hmac.new(self.private_key,
                                      query_params['ts'],
                                      sha1)
                query_params['api_sig'] = query_hmac.hexdigest()
                query_string = urlencode(query_params)

            if self.debug is True:
                print base + '?%s' % query_string
            return req_method(base + '?%s' % query_string,
                              headers=self.headers)

    @staticmethod
    def unicode2utf8(text):
        try:
            if isinstance(text, unicode):
                text = text.encode('utf-8')
        except:
            pass
        return text