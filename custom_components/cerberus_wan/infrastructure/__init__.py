"""Adapters: the protocols of the domain, implemented against the real world.

Everything that knows about DNS, about resolvers and about timeouts lives
here. The domain depends on this package in one direction only, and never by
importing it: it only ever sees the protocols in domain/ports.py.
"""
