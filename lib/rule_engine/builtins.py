#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  rule_engine/builtins.py
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are
#  met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following disclaimer
#    in the documentation and/or other materials provided with the
#    distribution.
#  * Neither the name of the project nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
#  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#  OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

import collections
import collections.abc
import datetime
import decimal
import functools
import math

from ._utils import parse_datetime, parse_timedelta
from . import ast

import dateutil.tz

def _builtin_filter(function, iterable):
	return tuple(filter(function, iterable))

def _builtin_map(function, iterable):
	return tuple(map(function, iterable))

def _builtin_parse_datetime(builtins, string):
	return parse_datetime(string, builtins.timezone)

class BuiltinValueGenerator(object):
	"""
	A class used as a wrapper for builtin values to differentiate between a value that is a function and a value that
	should be generated by calling a function. A value that is generated by calling a function is useful for determining
	the value during evaluation for things like the curren time.

	.. versionadded:: 4.0.0
	"""
	__slots__ = ('callable',)
	def __init__(self, callable):
		self.callable = callable

	def __call__(self, builtins):
		return self.callable(builtins)

class Builtins(collections.abc.Mapping):
	"""
	A class to define and provide variables to within the builtin context of rules. These can be accessed by specifying
	a symbol name with the ``$`` prefix.
	"""
	scope_name = 'built-in'
	"""The identity name of the scope for builtin symbols."""
	def __init__(self, values, namespace=None, timezone=None, value_types=None):
		"""
		:param dict values: A mapping of string keys to be used as symbol names with values of either Python literals or
			a function which will be called when the symbol is accessed. When using a function, it will be passed a
			single argument, which is the instance of :py:class:`Builtins`.
		:param str namespace: The namespace of the variables to resolve.
		:param timezone: A timezone to use when resolving timestamps.
		:type timezone: :py:class:`~datetime.tzinfo`
		:param dict value_types: A mapping of the values to their datatypes.

		.. versionchanged:: 2.3.0
			Added the *value_types* parameter.
		"""
		self.__values = values
		self.__value_types = value_types or {}
		self.namespace = namespace
		self.timezone = timezone or dateutil.tz.tzlocal()

	def resolve_type(self, name):
		"""
		The method to use for resolving the data type of a builtin symbol.

		:param str name: The name of the symbol to retrieve the data type of.
		:return: The data type of the symbol or :py:attr:`~rule_engine.ast.DataType.UNDEFINED`.
		"""
		return self.__value_types.get(name, ast.DataType.UNDEFINED)

	def __repr__(self):
		return "<{} namespace={!r} keys={!r} timezone={!r} >".format(self.__class__.__name__, self.namespace, tuple(self.keys()), self.timezone)

	def __getitem__(self, name):
		value = self.__values[name]
		if isinstance(value, collections.abc.Mapping):
			if self.namespace is None:
				namespace = name
			else:
				namespace = self.namespace + '.' + name
			return self.__class__(value, namespace=namespace, timezone=self.timezone)
		elif callable(value) and isinstance(value, BuiltinValueGenerator):
			value = value(self)
		return value

	def __iter__(self):
		return iter(self.__values)

	def __len__(self):
		return len(self.__values)

	@classmethod
	def from_defaults(cls, values=None, **kwargs):
		"""Initialize a :py:class:`Builtins` instance with a set of default values."""
		now = BuiltinValueGenerator(lambda builtins: datetime.datetime.now(tz=builtins.timezone))
		# there may be errors here if the decimal.Context precision exceeds what is provided by the math constants
		default_values = {
			# mathematical constants
			'e': decimal.Decimal(repr(math.e)),
			'pi': decimal.Decimal(repr(math.pi)),
			# timestamps
			'now': now,
			'today': BuiltinValueGenerator(lambda builtins: now(builtins).replace(hour=0, minute=0, second=0, microsecond=0)),
			# functions
			'any': any,
			'all': all,
			'sum': sum,
			'map': _builtin_map,
			'filter': _builtin_filter,
			'parse_datetime': BuiltinValueGenerator(lambda builtins: functools.partial(_builtin_parse_datetime, builtins)),
			'parse_timedelta': parse_timedelta
		}
		default_values.update(values or {})
		default_value_types = {
			# mathematical constants
			'e': ast.DataType.FLOAT,
			'pi': ast.DataType.FLOAT,
			# timestamps
			'now': ast.DataType.DATETIME,
			'today': ast.DataType.DATETIME,
			# functions
			'all': ast.DataType.FUNCTION('all', return_type=ast.DataType.BOOLEAN, argument_types=(ast.DataType.ARRAY,)),
			'any': ast.DataType.FUNCTION('any', return_type=ast.DataType.BOOLEAN, argument_types=(ast.DataType.ARRAY,)),
			'sum': ast.DataType.FUNCTION('sum', return_type=ast.DataType.FLOAT, argument_types=(ast.DataType.ARRAY(ast.DataType.FLOAT),)),
			'map': ast.DataType.FUNCTION('map', argument_types=(ast.DataType.FUNCTION, ast.DataType.ARRAY)),
			'filter': ast.DataType.FUNCTION('filter', argument_types=(ast.DataType.FUNCTION, ast.DataType.ARRAY)),
			'parse_datetime': ast.DataType.FUNCTION('parse_datetime', return_type=ast.DataType.DATETIME, argument_types=(ast.DataType.STRING,)),
			'parse_timedelta': ast.DataType.FUNCTION('parse_timedelta', return_type=ast.DataType.TIMEDELTA, argument_types=(ast.DataType.STRING,))
		}
		default_value_types.update(kwargs.pop('value_types', {}))
		return cls(default_values, value_types=default_value_types, **kwargs)
