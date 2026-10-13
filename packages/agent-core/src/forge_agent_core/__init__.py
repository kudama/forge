"""Trusted in-process dispatch; transport authenticates, domain adapters own data."""
from .core import Agent, Context, Grant, Principal, Reply, Request, Source, Tool

__all__ = ['Agent', 'Context', 'Grant', 'Principal', 'Reply', 'Request', 'Source', 'Tool']
