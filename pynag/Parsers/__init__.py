# -*- coding: utf-8 -*-

import sys
import os
import re

"""
Python Nagios extensions
"""

__author__ = "Drew Stinnett"
__copyright__ = "Copyright 2008, Drew Stinnett"
__credits__ = ["Drew Stinnett", "Pall Sigurdsson"]
__license__ = "GPL"
__version__ = "0.3"
__maintainer__ = "Pall Sigurdsson"
__email__ = "palli@opensource.is"
__status__ = "Development"

def debug(text):
	debug = True
	if debug: print text


class config:
	"""
	Parse and write nagios config files
	"""
	def __init__(self, cfg_file = "/etc/nagios/nagios.cfg"):

		self.cfg_file = cfg_file
		self.cfg_files = []
		self.data = {}
		self.item_list = None
		self.item_cache = None

		## This is a pure listof all the key/values in the config files.  It
		## shouldn't be useful until the items in it are parsed through with the proper
		## 'use' relationships
		self.pre_object_list = []
		self.post_object_list = []
		self.object_type_keys = {
			'hostgroup':'hostgroup_name',
			'hostextinfo':'host_name',
			'host':'host_name',
			'service':'name',
			'servicegroup':'servicegroup_name',
			'contact':'contact_name',
			'contactgroup':'contactgroup_name',
			'timeperiod':'timeperiod_name',
			'command':'command_name',
			#'service':['host_name','description'],
		}

		if not os.path.isfile(self.cfg_file):
			sys.stderr.write("%s does not exist\n" % self.cfg_file)
			return None

	def _has_template(self, target):
		"""
		Determine if an item has a template associated with it
		"""
		if target.has_key('use'):
			return True
		else:
			return None

	def _get_hostgroup(self, hostgroup_name):
		for hostgroup in self.data['all_hostgroup']:
			if hostgroup.has_key('hostgroup_name') and hostgroup['hostgroup_name'] == hostgroup_name:
				return hostgroup
		return None
	def _get_key(self, object_type, user_key = None):
		"""
		Return the correct 'key' for an item.  This is mainly a helper method
		for other methods in this class.  It is used to shorten code repitition
		"""
		if not user_key and not self.object_type_keys.has_key(object_type):
			sys.stderr.write("Unknown key for object type:  %s\n" % object_type)
			sys.exit(2)

		## Use a default key
		if not user_key:
			user_key = self.object_type_keys[object_type]

		return user_key
	
	def _get_item(self, item_name, item_type):
		""" 
   		Return an item from a list
   		"""
		# create local cache for performance optimizations. TODO: Rewrite functions that call this function
		if not self.item_list:
			self.item_list = self.pre_object_list
			self.item_cache = {}
			for item in self.item_list:
				if not item.has_key('name'):
					continue
				name = item['name']
				tmp_item_type = (item['meta']['object_type'])
				if not self.item_cache.has_key( tmp_item_type ):
					self.item_cache[tmp_item_type] = {}
				self.item_cache[tmp_item_type][name] = item
		try:
			return self.item_cache[item_type][item_name]
		except:
			return None
		if self.item_cache[item_type].has_key(item_name):
			return self.item_cache[item_type][item_name]
		return None
		for test_item in self.item_list:  
			## Skip tems without a name
			if not test_item.has_key('name'):
				continue

			## Make sure there isn't an infinite loop going on
			try:
				if (test_item['name'] == item_name) and (test_item['meta']['object_type'] == item_type):
					return test_item
			except:
				print "Loop detected, exiting"
				sys.exit(2)

		## If we make it this far, it means there is no matching item
		return None

	def _apply_template(self, original_item):
		"""
		Apply all attributes of item named parent_name to "original_item".
		"""
		# TODO: Performance optimization. Don't recursively call _apply_template on hosts we have already
		# applied templates to. This needs more work.
		if not original_item.has_key('use'):
			return original_item
		object_type = original_item['meta']['object_type']
		# Performance tweak, if item has been parsed. Lets not do it again
		if original_item.has_key('name') and self.item_apply_cache[object_type].has_key( original_item['name'] ):
			return self.item_apply_cache[object_type][ original_item['name'] ]
		# End of performance tweak
		parent_names = original_item['use'].split(',')
		parent_items = []
		for parent_name in parent_names:
			parent_item = self._get_item( parent_name, object_type )
			if parent_item == None: 
				error_string = "Can not find any %s named %s\n" % (object_type,parent_name)
				error_string = error_string + self.print_conf(original_item)
				raise Exception(error_string)
			# Parent item probably has use flags on its own. So lets apply to parent first
			parent_item = self._apply_template( parent_item )
			parent_items.append( parent_item )
		for parent_item in parent_items:
			for k,v in parent_item.iteritems():
				if k == 'use':
					continue
				if k == 'register':
					continue
				if k == 'meta':
					continue
				if k == 'name':
					continue
				original_item['meta']['inherited_attributes'][k] = v
				if not original_item.has_key(k):
					original_item[k] = v
					original_item['meta']['template_fields'].append(k)
		if original_item.has_key('name'):
			self.item_apply_cache[object_type][ original_item['name'] ] = original_item
		return original_item

			
	def _get_items_in_file(self, filename):
		"""
		Return all items in the given file
		"""
		return_list = []
				
		for k in self.data.keys():
			for item in self[k]:
				if item['meta']['filename'] == filename:
					return_list.append(item)
		return return_list

	def _load_file(self, filename):
		## Set globals (This is stolen from the perl module)
		append = ""
		type = None
		current = None
		in_definition = {}

		for line in open(filename, 'rb').readlines():

			## Cleanup and line skips
			line = line.strip()
			if line == "":
				continue
			if line[0] == "#" or line[0] == ';':
				continue

			# append saved text to the current line
			if append:
				append += ' '
				line = append + line;
				append = None

			# end of object definition
			if line.find("}") != -1:

				in_definition = None
				append = line.split("}", 1)[1]

				self.pre_object_list.append(current)


				## Destroy the Nagios Object
				current = None
				continue

			# beginning of object definition
			boo_re = re.compile("define\s+(\w+)\s*{?(.*)$")
			m = boo_re.search(line)
			if m:
				object_type = m.groups()[0]
				#current = NObject(object_type, filename)
				current = {}
				current['meta'] = {}
				current['meta']['object_type'] = object_type
				current['meta']['filename'] = filename
				current['meta']['template_fields'] = []
				current['meta']['needs_commit'] = None
				current['meta']['delete_me'] = None
				current['meta']['defined_attributes'] = {}
				current['meta']['inherited_attributes'] = {}

				if in_definition:
					sys.stderr.write("Error: Unexpected start of object definition in file '%s' on line $line_no.  Make sure you close preceding objects before starting a new one.\n" % filename)
					sys.exit(2)

				## Start off an object
				in_definition = True
				append = m.groups()[1]
				continue

			## save whatever's left in the buffer for the next iteration
			if not in_definition:
				append = line
				continue

			## this is an attribute inside an object definition
			if in_definition:
				#(key, value) = line.split(None, 1)
				tmp = line.split(None, 1)
				if len(tmp) > 1:
					(key, value) = tmp
				else:
					key = tmp[0]
					value = ""

				## Strip out in-line comments
				if value.find(";") != -1:
					value = value.split(";", 1)[0]

				## Clean info
				key = key.strip()
				value = value.strip()

				## Rename some old values that may be in the configuration
				## This can probably be removed in the future to increase performance
				if (current['meta']['object_type'] == 'service') and key == 'description':
					key = 'service_description'

				current[key] = value
				current['meta']['defined_attributes'][key] = value
			## Something is wrong in the config
			else:
				sys.stderr.write("Error: Unexpected token in file '%s'" % filename)
				sys.exit(2)

		## Something is wrong in the config
		if in_definition:
			sys.stderr.write("Error: Unexpected EOF in file '%s'" % filename)
			sys.exit(2)
	def _locate_object(self, item):
		"""
		This is a helper function for anyone who wishes to modify objects. It takes "item", locates the
		file which is configured in, and locates exactly the lines which contain that definition.
		
		Returns tuple:
			(everything_before, object_definition, everything_after, filename)
			everything_before(string) - Every line in filename before object was defined
			everything_after(string) - Every line in "filename" after object was defined
			object_definition - exact configuration of the object as it appears in "filename"
			filename - file in which the object was written to
		Raises:
			ValueError if object was not found in "filename"
		"""
		if item['meta'].has_key("filename"):
			filename = item['meta']['filename']
		else:
			raise ValueError("item does not have a filename")
		file = open(filename)
		object_has_been_found = False
		everything_before = [] # Every line before our object definition
		everything_after = []  # Every line after our object definition
		object_definition = [] # List of every line of our object definition
		i_am_within_definition = False
		for line in file.readlines():
			if object_has_been_found:
				everything_after.append( line )
				continue
			tmp  = line.split(None, 1)
			if len(tmp) == 0:
				keyword = ''
				rest = ''
			if len(tmp) == 1:
				keyword = tmp[0]
				rest = ''
			if len(tmp) > 1:
				keyword,rest = tmp[0],tmp[1]
			keyword = keyword.strip()
			# If we reach a define statement, we log every line to a special buffer
			# When define closes, we parse the object and see if it is the object we
			# want to modify
			if keyword == 'define':
				current_object_type = rest.split(None,1)[0]
				current_object_type = current_object_type.strip(';')
				current_object_type = current_object_type.strip('{')
				current_object_type = current_object_type.strip()
				tmp_buffer = []
				i_am_within_definition = True
			if i_am_within_definition == True:
				tmp_buffer.append( line )
			else:
				everything_before.append( line )
			if len(keyword) > 0 and keyword[0] == '}':
				i_am_within_definition = False
				current_definition = {}
				current_definition['meta'] = {'object_type':current_object_type}
				current_definition['meta']['template_fields'] = []
				current_definition['meta']['filename'] = item['meta']['filename']
				current_definition['meta']['defined_attributes'] = {}
				current_definition['meta']['inherited_attributes'] = {}
				for i in tmp_buffer:
					i = i.strip()
					tmp = i.split(None, 1)
					if len(tmp) == 1:
						k = tmp[0]
						v = ''
					elif len(tmp) > 1:
						k,v = tmp[0],tmp[1]
						v = v.split(';',1)[0]
						v = v.strip()
					else: continue # skip empty lines
					
					if k.startswith('#'): continue
					if k.startswith(';'): continue
					if k.startswith('define'): continue
					if k.startswith('}'): continue
					
					current_definition[k] = v
					current_definition = self._apply_template(current_definition)
				# Compare objects
				if self.compareObjects( item, current_definition ) == True:
					'This is the object i am looking for'
					object_has_been_found = True
					object_definition = tmp_buffer
		if object_has_been_found:
			return (everything_before, object_definition, everything_after, filename)
		else:
			raise ValueError("We could not find object in %s" % filename)
	def _modify_object(self, item, field_name=None, new_value=None, new_field_name=None, new_item=None):
		'''
		Helper function for object_* functions. Locates "item" and changes the line which contains field_name.
		If new_value and new_field_name are both None, the attribute is removed.
		
		Arguments:
			item(dict) -- The item to be modified
			field_name(str) -- The field_name to modify (if any)
			new_field_name(str) -- If set, field_name will be renamed
			new_value(str) -- If set the value of field_name will be changed
			new_item(str) -- If set, whole object will be replaced with this string
		Returns:
			True on success
		Raises:
			ValueError if object or field_name is not found
			IOError is save is unsuccessful.
		'''
		if field_name is None and new_item is None:
			raise ValueError("either field_name or new_item must be set")
		everything_before,object_definition, everything_after, filename = self._locate_object(item)
		if new_item is not None:
			'We have instruction on how to write new object, so we dont need to parse it'
			change = True
			object_definition = [new_item]
		else:
			change = None
			for i in range( len(object_definition)):
				tmp = object_definition[i].split(None, 1)
				if len(tmp) == 0: continue
				if len(tmp) == 1: value = ''
				if len(tmp) == 2: value = tmp[1]
				k = tmp[0].strip()
				if k == field_name:
					'Attribute was found, lets change this line'
					if not new_field_name and not new_value:
						'We take it that we are supposed to remove this attribute'
						change = object_definition.pop(i)
						break
					elif new_field_name:
						'Field name has changed'
						k = new_field_name
					if new_value:
						'value has changed '
						value = new_value
					# Here we do the actual change	
					change = "\t %-30s %s\n" % (k, value)
					object_definition[i] = change
					break
			if not change:
					'Attribute was not found, lets throw up an exception indicating the field was not found'
					raise ValueError( 'attribute %s was not found.' % field_name)

		# Here we overwrite the config-file, hoping not to ruin anything
		buffer = "%s%s%s" % (''.join(everything_before), ''.join(object_definition), ''.join(everything_after))
		file = open(filename,'w')
		file.write( buffer )
		file.close()
		return True		
	def object_rewrite(self, item, str_new_item):
		"""
		Completely rewrites item with string provided.
		
		Arguments:
			item -- Item that is to be rewritten
			str_new_item -- str representation of the new item
		Examples:
			object_rewrite( item, "define service {\n name example-service \n register 0 \n }\n" )
		Returns:
			True on success
		Raises:
			ValueError if object is not found
			IOError if save fails
		"""
		return self._modify_object(item=item, new_item=str_new_item)
	def object_remove(self, item):
		"""
		Completely rewrites item with string provided.
		
		Arguments:
			item -- Item that is to be rewritten
			str_new_item -- str representation of the new item
		Examples:
			object_rewrite( item, "define service {\n name example-service \n register 0 \n }\n" )
		Returns:
			True on success
		Raises:
			ValueError if object is not found
			IOError if save fails
		"""
		return self._modify_object(item=item, new_item="")

	def object_edit_field(self, item, field_name, new_value):
		"""
		Modifies one field of a (currently existing) object. Changes are immediate (i.e. there is no commit)
		
		Example usage:
			edit_object( item, field_name="host_name", new_value="examplehost.example.com")
		Returns:
			True on success
		Raises:
			ValueError if object is not found
			IOError if save fails
		"""
		return self._modify_object(item, field_name=field_name, new_value=new_value)
	
	def object_remove_field(self, item, field_name):
		"""
		Removes one field of a (currently existing) object. Changes are immediate (i.e. there is no commit)
		
		Example usage:
			object_remove_field( item, field_name="contactgroups" )
		Returns:
			True on success
		Raises:
			ValueError if object is not found
			IOError if save fails
		"""
		return self._modify_object(item=item, field_name=field_name, new_value=None, new_field_name=None)
	
	def object_rename_field(self, item, old_field_name, new_field_name):
		"""
		Renames a field of a (currently existing) item. Changes are immediate (i.e. there is no commit).
		
		Example usage:
			object_rename_field(item, old_field_name="normal_check_interval", new_field_name="check_interval")
		Returns:
			True on success
		Raises:
			ValueError if object is not found
			IOError if save fails
		"""
		return self._modify_object(item=item, field_name=old_field_name, new_field_name=new_field_name)
	def object_add(self, item, filename):
		"""
		Adds a new object to a specified config file
		
		Arguments:
			item -- Item to be created
			filename -- Filename that we are supposed to write to
		Returns:
			True on success
		Raises:
			IOError on failed save
		"""
		if not 'meta' in item:
			item['meta'] = {}
		item['meta']['filename'] = filename
		
		buffer = self.print_conf( item )
		file = open(filename,'a')
		file.write( buffer )
		file.close()
		return True		
			
	def edit_object(self,item, field_name, new_value):
		"""
		Modifies a (currently existing) item. Changes are immediate (i.e. there is no commit)
		
		Example Usage: edit_object( item, field_name="host_name", new_value="examplehost.example.com")
		
		THIS FUNCTION IS DEPRECATED. USE object_edit_field() instead
		"""
		return self.object_edit_field(item=item, field_name=field_name, new_value=new_value)

	def compareObjects(self, item1, item2):
		"""
		Compares two items. Returns true if they are equal"
		"""
		keys1 = item1.keys()
		keys2 = item2.keys()
		keys1.sort()
		keys2.sort()
		result=True
		if keys1 != keys2:
			return False
		for key in keys1:
			if key == 'meta': continue
			key1 = item1[key]
			key2 = item2[key]
			# For our purpose, 30 is equal to 30.000
			if key == 'check_interval':
				key1 = int(float(key1))
				key2 = int(float(key2))
			if key1 != key2:
				result = False
		if result == False: return False
		return True
	def edit_service(self, target_host, service_description, field_name, new_value):
		"""
		Edit a service's attributes
		"""

		original_object = self.get_service(target_host, service_description)
		if original_object == None:
			raise Exception("Service not found")
		return config.edit_object( original_object, field_name, new_value)


	def _get_list(self, object, key):
		"""
		Return a comma list from an item

		Example:

		_get_list(Foo_object, host_name)
		define service {
			service_description Foo
			host_name			larry,curly,moe
		}

		return
		['larry','curly','moe']
		"""
		if type(object) != type({}):
			sys.stderr.write("%s is not a dictionary\n" % object)
			return None
		if not object.has_key(key):
			return None

		return_list = []

		if object[key].find(",") != -1:
			for name in object[key].split(","):
				return_list.append(name)
		else:
			return_list.append(object[key])

		## Alphabetize
		return_list.sort()

		return return_list
		
	def delete_object(self, object_type, object_name, user_key = None):
		"""
		Delete object from configuration files.
		"""
		object_key = self._get_key(object_type,user_key)

		target_object = None
		k = 'all_%s' % object_type
		for item in self.data[k]:
			if not item.has_key(object_key):
				continue

			## If the object matches, mark it for deletion
			if item[object_key] == object_name:
				self.data[k].remove(item)
				item['meta']['delete_me'] = True
				item['meta']['needs_commit'] = True
				self.data[k].append(item)

				## Commit the delete
				self.commit()
				return True

		## Only make it here if the object isn't found
		return None

	def delete_service(self, service_description, host_name):
		"""
		Delete service from configuration
		"""
		for item in self.data['all_service']:
			if (item['service_description'] == service_description) and (host_name in self._get_active_hosts(item)):
				self.data['all_service'].remove(item)
				item['meta']['delete_me'] = True
				item['meta']['needs_commit'] = True
				self.data['all_service'].append(item)

				return True

	def delete_host(self, object_name, user_key = None):
		"""
		Delete a host
		"""
		return self.delete_object('host',object_name, user_key = user_key)

	def delete_hostgroup(self, object_name, user_key = None):
		"""
		Delete a hostgroup
		"""
		return self.delete_object('hostgroup',object_name, user_key = user_key)

	def get_object(self, object_type, object_name, user_key = None):
		"""
		Return a complete object dictionary
		"""
		object_key = self._get_key(object_type,user_key)

		target_object = None

		#print object_type
		for item in self.data['all_%s' % object_type]:
			## Skip items without the specified key
			if not item.has_key(object_key):
				continue
			if item[object_key] == object_name:
				target_object = item
			## This is for multi-key items
		return target_object

	def get_host(self, object_name, user_key = None):
		"""
		Return a host object
		"""
		return self.get_object('host',object_name, user_key = user_key)

	def get_servicegroup(self, object_name, user_key = None):
		"""
		Return a Servicegroup object
		"""
		return self.get_object('servicegroup',object_name, user_key = user_key)

	def get_contact(self, object_name, user_key = None):
		"""
		Return a Contact object
		"""
		return self.get_object('contact',object_name, user_key = user_key)

	def get_contactgroup(self, object_name, user_key = None):
		"""
		Return a Contactgroup object
		"""
		return self.get_object('contactgroup',object_name, user_key = user_key)

	def get_timeperiod(self, object_name, user_key = None):
		"""
		Return a Timeperiod object
		"""
		return self.get_object('timeperiod',object_name, user_key = user_key)

	def get_command(self, object_name, user_key = None):
		"""
		Return a Command object
		"""
		return self.get_object('command',object_name, user_key = user_key)

	def get_hostgroup(self, object_name, user_key = None):
		"""
		Return a hostgroup object
		"""
		return self.get_object('hostgroup',object_name, user_key = user_key)

	def get_service(self, target_host, service_description):
		"""
		Return a service object.  This has to be seperate from the 'get_object'
		method, because it requires more than one key
		"""
		for item in self.data['all_service']:
			## Skip service with no service_description
			if not item.has_key('service_description'):
				continue
			## Skip non-matching services
			if item['service_description'] != service_description:
				continue

			if target_host in self._get_active_hosts(item):
				return item

		return None

	def _append_use(self, source_item, name):
		"""
		Append any unused values from 'name' to the dict 'item'
		"""
		## Remove the 'use' key
		if source_item.has_key('use'):
			del source_item['use']
		
		for possible_item in self.pre_object_list:
			if possible_item.has_key('name'):
				## Start appending to the item
				for k,v in possible_item.iteritems():

					try:
						if k == 'use':
							source_item = self._append_use(source_item, v)
					except:
						print "Recursion error on %s %s" % (source_item, v)
						sys.exit(2)

					## Only add the item if it doesn't already exist
					if not source_item.has_key(k):
						source_item[k] = v
		return source_item

	def _post_parse(self):
		self.item_list = None
		self.item_apply_cache = {} # This is performance tweak used by _apply_template
		for raw_item in self.pre_object_list:
			# Performance tweak, make sure hashmap exists for this object_type
			object_type = raw_item['meta']['object_type']
			if not self.item_apply_cache.has_key( object_type ):
				self.item_apply_cache[ object_type ] = {}
			# Tweak ends
			if raw_item.has_key('use'):
				raw_item = self._apply_template( raw_item )
			self.post_object_list.append(raw_item)
		## Add the items to the class lists.  
		for list_item in self.post_object_list:
			type_list_name = "all_%s" % list_item['meta']['object_type']
			if not self.data.has_key(type_list_name):
				self.data[type_list_name] = []

			self.data[type_list_name].append(list_item)
	def commit(self):
		"""
		Write any changes that have been made to it's appropriate file
		"""
		## Loops through ALL items
		for k in self.data.keys():
			for item in self[k]:

				## If the object needs committing, commit it!
				if item['meta']['needs_commit']:
					## Create file contents as an empty string
					file_contents = ""

					## find any other items that may share this config file
					extra_items = self._get_items_in_file(item['meta']['filename'])
					if len(extra_items) > 0:
						for commit_item in extra_items:
							## Ignore files that are already set to be deleted:w
							if commit_item['meta']['delete_me']:
								continue
							## Make sure we aren't adding this thing twice
							if item != commit_item:
								file_contents += self.print_conf(commit_item)

					## This is the actual item that needs commiting
					if not item['meta']['delete_me']:
						file_contents += self.print_conf(item)

					## Write the file
					f = open(item['meta']['filename'], 'w')
					f.write(file_contents)
					f.close()

					## Recreate the item entry without the commit flag
					self.data[k].remove(item)
					item['meta']['needs_commit'] = None
					self.data[k].append(item)

	def flag_all_commit(self):
		"""
		Flag every item in the configuration to be committed
		This should probably only be used for debugging purposes
		"""
		for k in self.data.keys():
			index = 0
			for item in self[k]:
				self.data[k][index]['meta']['needs_commit'] = True
				index += 1

	def print_conf(self, item):
		"""
		Return a string that can be used in a configuration file
		"""
		import time

		output = ""
		## Header, to go on all files
		output += "# Configuration file %s\n" % item['meta']['filename']
		output += "# Edited by PyNag on %s\n" % time.ctime()

		## Some hostgroup information
		if item['meta'].has_key('hostgroup_list'):
			output += "# Hostgroups: %s\n" % ",".join(item['meta']['hostgroup_list'])

		## Some hostgroup information
		if item['meta'].has_key('service_list'):
			output += "# Services: %s\n" % ",".join(item['meta']['service_list'])

		## Some hostgroup information
		if item['meta'].has_key('service_members'):
			output += "# Service Members: %s\n" % ",".join(item['meta']['service_members'])

		if len(item['meta']['template_fields']) != 0:
			output += "# Values from templates:\n"
		for k in item['meta']['template_fields']:
			output += "#\t %-30s %-30s\n" % (k, item[k])
		output += "\n"
		output += "define %s {\n" % item['meta']['object_type']
		for k, v in item.iteritems():
			if k != 'meta':
				if k not in item['meta']['template_fields']:
					output += "\t %-30s %-30s\n" % (k,v)
		
		output += "}\n\n"
		return output



	def parse(self):
		"""
		Load the nagios.cfg file and parse it up
		"""
		for line in open(self.cfg_file).readlines():
			## Strip out new line characters
			line = line.strip()

			## Skip blank lines
			if line == "":
				continue

			## Skip comments
			if line[0] == "#" or line[0] == ';':
				continue

			## Now get the actual objects and values
			(config_object, config_value) = line.split("=", 1)

			## Add cfg_file objects to cfg file list
			if config_object == "cfg_file" and os.path.isfile(config_value):
					self.cfg_files.append(config_value)

			## Parse all files in a cfg directory
			if config_object == "cfg_dir":
				directories = []
				raw_file_list = []
				directories.append( config_value )
				# Walk through every subdirectory and add to our list
				while len(directories) > 0:
					current_directory = directories.pop(0)
					list = os.listdir(current_directory)
					for item in list:
						# Append full path to file
						item = "%s" % (os.path.join(current_directory, item.strip() ) )
						if os.path.islink( item ):
							item = os.readlink( item )
						if os.path.isdir(item):
							directories.append( item )
						if raw_file_list.count( item ) < 1:
							raw_file_list.append( item )
				for raw_file in raw_file_list:
					if raw_file.endswith('.cfg'):
						if os.path.exists(raw_file):
							self.cfg_files.append(raw_file)

		## This loads everything into
		for cfg_file in self.cfg_files:
			self._load_file(cfg_file)

		self._post_parse()

	def extended_parse(self):
		"""
		This parse is used after the initial parse() command is run.  It is
		only needed if you want extended meta information about hosts or other objects
		"""
		## Do the initial parsing
		self.parse()

		## First, cycle through the hosts, and append hostgroup information
		index = 0
		for host in self.data['all_host']:
			if not self.data['all_host'][index]['meta'].has_key('hostgroup_list'):
				self.data['all_host'][index]['meta']['hostgroup_list'] = []

			## Append any hostgroups that are directly listed in the host definition
			if host.has_key('hostgroups'):
				for hostgroup_name in self._get_list(host, 'hostgroups'):
					if not self.data['all_host'][index]['meta'].has_key('hostgroup_list'):
						self.data['all_host'][index]['meta']['hostgroup_list'] = []
					if hostgroup_name not in self.data['all_host'][index]['meta']['hostgroup_list']:
						self.data['all_host'][index]['meta']['hostgroup_list'].append(hostgroup_name)

			## Append any services which reference this host
			service_list = []
			for service in self.data['all_service']:
				if host['host_name'] in self._get_active_hosts(service):
					service_list.append(service['service_description'])
			self.data['all_host'][index]['meta']['service_list'] = service_list
					

			## Increment count
			index += 1

		## Loop through all hostgroups, appending them to their respective hosts
		for hostgroup in self.data['all_hostgroup']:

			for member in self._get_list(hostgroup,'members'):
				index = 0
				for host in self.data['all_host']:

					## Skip members that do not match
					if host['host_name'] == member:

						## Create the meta var if it doesn' exist
						if not self.data['all_host'][index]['meta'].has_key('hostgroup_list'):
							self.data['all_host'][index]['meta']['hostgroup_list'] = []

						if hostgroup['hostgroup_name'] not in self.data['all_host'][index]['meta']['hostgroup_list']:
							self.data['all_host'][index]['meta']['hostgroup_list'].append(hostgroup['hostgroup_name'])

					## Increment count
					index += 1

		## Expand service membership
		index = 0
		for service in self.data['all_service']:
			service_members = []

			## Find a list of hosts to negate from the final list
			self.data['all_service'][index]['meta']['service_members'] = self._get_active_hosts(service)

			## Increment count
			index += 1

	def _get_active_hosts(self, object):
		"""
		Given an object, return a list of active hosts.  This will exclude hosts that ar negated with a "!"
		"""
		## First, generate the negation list
		negate_hosts = []

		## Hostgroups
		if object.has_key("hostgroup_name"):

			for hostgroup_name in self._get_list(object, 'hostgroup_name'):
				if hostgroup_name[0] == "!":
					hostgroup_obj = self.get_hostgroup(hostgroup_name[1:])
					negate_hosts.extend(self._get_list(hostgroup_obj,'members'))

		## Host Names
		if object.has_key("host_name"):
			for host_name in self._get_list(object, 'host_name'):
				if host_name[0] == "!":
					negate_hosts.append(host_name[1:])


		## Now get hosts that are actually listed
		active_hosts = []

		## Hostgroups
		if object.has_key("hostgroup_name"):

			for hostgroup_name in self._get_list(object, 'hostgroup_name'):
				if hostgroup_name[0] != "!":
					active_hosts.extend(self._get_list(self.get_hostgroup(hostgroup_name),'members'))

		## Host Names
		if object.has_key("host_name"):
			for host_name in self._get_list(object, 'host_name'):
				if host_name[0] != "!":
					active_hosts.append(host_name)

		## Combine the lists
		return_hosts = []
		for active_host in active_hosts:
			if active_host not in negate_hosts:
				return_hosts.append(active_host)

		return return_hosts

	def get_cfg_files(self):
		"""
		Return a list of all cfg files used in this configuration

		Example:
		print get_cfg_files()
		['/etc/nagios/hosts/host1.cfg','/etc/nagios/hosts/host2.cfg',...]
		"""
		return self.cfg_files

	def cleanup(self):
		"""
		This cleans up dead configuration files
		"""
		for filename in self.cfg_files:
			if os.path.isfile(filename):
				size = os.stat(filename)[6]
				if size == 0:
					os.remove(filename)

		return True

	def __setitem__(self, key, item):
		self.data[key] = item

	def __getitem__(self, key):
		return self.data[key]

class status:

	def __init__(self, filename = "/var/log/nagios/status.dat"):

		if not os.path.isfile(filename):
			sys.stderr.write("Missing stat file %s" % filename)

		self.filename = filename
		self.data = {}

	def parse(self):
		## Set globals (This is stolen from the perl module)
		type = None

		for line in open(self.filename, 'rb').readlines():

			## Cleanup and line skips
			line = line.strip()
			if line == "":
				continue
			if line[0] == "#" or line[0] == ';':
				continue

			if line.find("{") != -1:

				status = {}
				status['meta'] = {}
				status['meta']['type'] = line.split("{")[0].strip()
				continue

			if line.find("}") != -1:
				if not self.data.has_key(status['meta']['type']):
					self.data[status['meta']['type']] = []
	
				self.data[status['meta']['type']].append(status)
				continue

			(key, value) = line.split("=", 1)
			status[key] = value


	def __setitem__(self, key, item):
		self.data[key] = item

	def __getitem__(self, key):
		return self.data[key]

if __name__ == '__main__':
	c=config('/etc/nagios/nagios.cfg')
	c.parse()
	#for i in c.data['all_host']:
	#	print i['meta']
