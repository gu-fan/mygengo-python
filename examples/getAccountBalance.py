# -*- coding: utf-8 -*-
#!/usr/bin/python

from mygengo import MyGengo

# Get an instance of MyGengo to work with...
gengo = MyGengo(
    public_key = 'your_public_key',
    private_key = 'your_private_key'
    sandbox = False, # possibly false, depending on your dev needs
	debug = True
)

# Retrieve and print the account balance. Properties ahoy!
print gengo.getAccountBalance()
