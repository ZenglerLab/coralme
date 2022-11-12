import coralme

def get_base_complex_data(model, complex_id):
	"""If a complex is modified in a metabolic reaction it will not
	have a formation reaction associated with it. This function returns
	the complex data of the "base" complex, which will have the subunit
	stoichiometry of that complex"""

	# First try unmodified complex id
	try_1 = complex_id.split('_mod_')[0]
	if try_1 in model.process_data:
		return model.process_data.get_by_id(try_1)

	count = 0
	try_2 = complex_id.split('_mod_')[0] + '_'
	for i in model.process_data.query(try_2):
		if isinstance(i, coralme.core.processdata.ComplexData):
			count += 1
			data = i

	if count == 0:
		raise UserWarning('No base complex found for \'{:s}\'.'.format(complex_id))

	elif count > 1:
		raise UserWarning('More than one possible base complex found for \'{:s}\'.'.format(complex_id))

	return data
