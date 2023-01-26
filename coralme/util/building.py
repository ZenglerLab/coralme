import tqdm
bar_format = '{desc:<75}: {percentage:.1f}%|{bar}| {n_fmt:>5}/{total_fmt:>5} [{elapsed}<{remaining}]'
import pandas
import logging

import coralme

# read genbank and extract sequences and data
import Bio
from Bio import SeqIO, Seq, SeqFeature, SeqUtils

def add_transcription_reaction(me_model, tu_name, locus_ids, sequence, organelle = None, update = True):
	"""
	Create TranscriptionReaction object and add it to ME-model.
	This includes the necessary transcription data.

	Parameters
	----------
	me_model : :class:`coralme.core.model.MEModel`
		The MEModel object to which the reaction will be added

	tu_name : str
		ID of TU being transcribed.
		The TranscriptionReaction will be added as "transcription_+TU_name"
		The TranscriptionData will be added as just 'TU_name'

	locus_ids : set
		Set of locus IDs that the TU transcribes

	sequence : str
		Nucleotide sequence of the TU.

	update : bool
		If True, use TranscriptionReaction's update function to update and
		add reaction stoichiometry

	Returns
	-------
	:class:`coralme.core.reaction.TranscriptionReaction`
		TranscriptionReaction for the TU
	"""

	transcription = coralme.core.reaction.TranscriptionReaction('transcription_' + tu_name)
	transcription.transcription_data = coralme.core.processdata.TranscriptionData(tu_name, me_model)
	transcription.transcription_data.nucleotide_sequence = sequence
	transcription.transcription_data.RNA_products = {'RNA_' + i for i in locus_ids}
	# Necessary for eukaryotes where transcription can occur in the nucleus, mitochondria or chloroplasts
	transcription.transcription_data.organelle = organelle

	me_model.add_reactions([transcription])
	if update:
		transcription.update()
	return transcription

def create_transcribed_gene(me_model, locus_id, rna_type, seq, left_pos = None, right_pos = None, strand = None):
	"""
	 Creates a `TranscribedGene` metabolite object and adds it to the ME-model

	Parameters
	----------
	me_model : :class:`coralme.core.model.MEModel`
		The MEModel object to which the reaction will be added

	locus_id : str
		Locus ID of RNA product.
		The TranscribedGene will be added as "RNA + _ + locus_id"

	left_pos : int or None
		Left position of gene on the sequence of the (+) strain

	right_pos : int or None
		Right position of gene on the sequence of the (+) strain

	seq : str
		Nucleotide sequence of RNA product.
		Amino acid sequence, codon counts, etc. will be calculated based on
		this string.

	strand : str or None
		- (+) if the RNA product is on the leading strand
		- (-) if the RNA product is on the complementary strand

	rna_type : str
		Type of RNA of the product.
		tRNA, rRNA, or mRNA
		Used for determining how RNA product will be processed.

	Returns
	-------
		:class:`coralme.core.component.TranscribedGene`
			Metabolite object for the RNA product
	"""
	gene = coralme.core.component.TranscribedGene('RNA_' + locus_id, rna_type, seq)
	gene.left_pos = left_pos.split(',') if left_pos is not None else None
	gene.right_pos = right_pos.split(',') if right_pos is not None else None
	gene.strand = strand

	if len(me_model.metabolites.query('^RNA_{:s}$'.format(locus_id))) != 0:
		me_model.metabolites._replace_on_id(gene)
		logging.warning('TranscribedGene \'{:s}\' was replaced.'.format(gene.id))

	me_model.add_metabolites([gene])

	return None

def add_translation_reaction(me_model, locus_id, dna_sequence, prot_sequence = '', organelle = None, transl_table = 1, update = False):
	"""
	Creates and adds a TranslationReaction to the ME-model as well as the
	associated TranslationData

	A dna_sequence is required in order to add a TranslationReaction to the
	ME-model

	Parameters
	----------
	me_model : :class:`coralme.core.model.MEModel`
		The MEModel object to which the reaction will be added

	locus_id : str
		Locus ID of RNA product.
		The TranslationReaction will be added as "translation + _ + locus_id"
		The TranslationData will be added as 'locus_id'

	dna_sequence : str
		DNA sequence of the RNA product. This string should be reverse
		transcribed if it originates on the complement strand.

	update : bool
		If True, use TranslationReaction's update function to update and
		add reaction stoichiometry

	"""

	# Create TranslationData
	translation_data = coralme.core.processdata.TranslationData(locus_id, me_model, 'RNA_' + locus_id, 'protein_' + locus_id)
	translation_data.nucleotide_sequence = dna_sequence
	translation_data.organelle = organelle
	translation_data.translation = prot_sequence
	translation_data.transl_table = Bio.Data.CodonTable.generic_by_id[transl_table]

	# Add RNA to model if it doesn't exist
	if 'RNA_' + locus_id not in me_model.metabolites:
		logging.warning('RNA_{:s} not present in ME-model and it was created.'.format(locus_id))
		rna = coralme.core.component.TranscribedGene('RNA_' + locus_id, 'mRNA', dna_sequence)
		me_model.add_metabolites(rna)

	# Create and add TranslationReaction with TranslationData
	translation_reaction = coralme.core.reaction.TranslationReaction('translation_' + locus_id)
	me_model.add_reactions([translation_reaction])
	translation_reaction.translation_data = translation_data

	if update:
		translation_reaction.update()

	return None

def convert_aa_codes_and_add_charging(me_model, trna_aa, trna_to_codon, organelle, verbose = True):
	"""
	Adds tRNA charging reactions for all tRNAs in ME-model

	Parameters
	----------
	me_model : :class:`coralme.core.model.MEModel`
		The MEModel object to which the reaction will be added

	trna_aa : dict
		Dictionary of tRNA locus ID to 3 letter codes of the amino acid
		that the tRNA contributes

		{tRNA identifier (locus_id): amino_acid_3_letter_code}

	trna_to_codon : dict
		Dictionary of tRNA identifier to the codon which it associates

		{tRNA identifier (locus_id): codon_sequence}

	verbose : bool
		If True, display metabolites that were not previously added to the
		model and were thus added when creating charging reactions
	"""

	# remove "other" tRNAs: This avoids a RuntimeError: dictionary changed size during iteration using pop
	trna_aa = { k:v for k,v in trna_aa.items() if v.lower() != 'other' }

	# convert amino acid 3 letter codes to metabolites
	#for tRNA, aa in list(iteritems(trna_aa)):
	for tRNA, aa in trna_aa.items():
		if aa.lower() == 'other':
			pass
			#trna_aa.pop(tRNA) # RuntimeError: dictionary changed size during iteration
		elif aa.lower() == 'sec':
			# Charge with precursor to selenocysteine
			trna_aa[tRNA] = me_model.metabolites.get_by_id('ser__L_' + organelle)
		elif aa.lower() == 'gly':
			trna_aa[tRNA] = me_model.metabolites.get_by_id('gly_' + organelle)
		else:
			if me_model.metabolites.has_id(aa.lower() + '__L_' + organelle):
				trna_aa[tRNA] = me_model.metabolites.get_by_id(aa.lower() + '__L_' + organelle)
			else:
				logging.warning('The \'{:s}\' metabolite does not exist in the ME-model.'.format(aa.lower() + '__L_' + organelle))

	# check trna_to_codon for START codon
	start = False
	for tRNA, codon in trna_to_codon.items():
		if 'START' in codon:
			start = True
	if not start:
		logging.warning('Associate at least one tRNA-Met/tRNA-fMet gene with the \'START\' keyword or add manually a \'tRNAChargingReaction\'.')

	# add in all the tRNA charging reactions
	for tRNA, aa in trna_aa.items():
		if tRNA not in trna_to_codon.keys() or isinstance(aa, str): # trna_to_codon contains all the tRNAs found in the organism, not per organelle
			continue

		if not me_model.metabolites.has_id(aa.id):
			continue

		for codon in trna_to_codon[tRNA]:
			codon = codon.replace('T', 'U') if codon != 'START' else codon
			trna_data = coralme.core.processdata.tRNAData('tRNA_{:s}_{:s}'.format(tRNA, codon), me_model, aa.id, 'RNA_' + tRNA, codon)
			charging_reaction = coralme.core.reaction.tRNAChargingReaction('charging_tRNA_{:s}_{:s}'.format(tRNA, codon))
			charging_reaction.tRNA_data = trna_data
			charging_reaction.organelle = organelle

			me_model.add_reactions([charging_reaction])
			charging_reaction.update(verbose = verbose)

	return None

def build_reactions_from_genbank(
	me_model, gb_filename, tu_frame = pandas.DataFrame(columns = ['genes']), genes_to_add = list(),
	feature_types = [ 'CDS', 'rRNA', 'tRNA', 'ncRNA', 'tmRNA' ], update = True, verbose = True,
	trna_misacylation = dict(), genome_mods = dict(), knockouts = list()):
	# trna_to_codon = dict(), frameshift_dict = None, # not needed anymore

	"""Creates and adds transcription and translation reactions using genomic
	 information from the organism's genbank file. Adds in the basic
	 requirements for these reactions. Organism specific components are added.

	Parameters
	----------
	me_model : :class:`coralme.core.model.MEModel`
		The MEModel object to which the reaction will be added

	gb_filename : str
		Local name of the genbank file that will be used for ME-model
		construction

	tu_frame : :class:`pandas.DataFrame`
		DataFrame with indexes of the transcription unit name and columns
		containing the transcription unit starting and stopping location on
		the genome and whether the transcription unit is found on the
		main (+) strand or complementary (-) strand.

		If no transcription unit DataFrame is passed into the function,
		transcription units are added corresponding to each transcribed
		gene in the genbank file.

	element_types : set
		Transcription reactions will be added to the ME-model for all RNA
		feature.types in this set. This uses the nomenclature of the
		genbank file (gb_filename)

	verbose : bool
		If True, display metabolites that were not previously added to the
		model and were thus added when creating charging reactions
	"""
	# old docstring
	#frameshift_dict : dict
		#{locus_id: genome_position_of_TU}

		#If a locus_id is in the frameshift_dict, update it's nucleotide
		#sequence to account of the frameshift

	#if not trna_to_codon:
		#trna_to_codon = {}

	#metabolites = me_model.metabolites

	# Load genbank file and extract DNA sequence
	#try:
		#seqs = SeqIO.read(gb_filename, 'gb')
		#full_seqs = str(seqs.seq)
	#except:
	contigs = []
	if isinstance(gb_filename, str):
		gb_filename = [gb_filename]
	for infile in gb_filename:
		for contig in SeqIO.parse(infile, 'gb'):
			contigs.append(contig)
	full_seqs = { x.id:x.seq for x in contigs }

	# GC Content
	if me_model.global_info.get('GC_fraction', None) is None:
		me_model.global_info['GC_fraction'] = SeqUtils.GC(''.join([ str(x) for x in full_seqs.values()]))

	# modify sequence(s) using genome_mods dictionary
	for replicon, coords in genome_mods.items():
		new = full_seqs[replicon]
		for segment in coords.split(';'):
			if segment.startswith('DEL:'):
				x = segment[4:].split('..')
				new = ''.join([ '-' if idx in range(int(x[0])-1, int(x[1])) else nucl for idx,nucl in enumerate(new) ])
			elif segment.startswith('INS:'):
				raise NotImplementedError
			elif segment[0] in ['A', 'T', 'C', 'G'] and segment[-1] in ['A', 'T', 'C', 'G'] and segment[1:-1].isdigit():
				new[int(segment[1:-1])-1] = segment[-1]
			else:
				x = segment.split(':')
				if len(x[0]) == len(x[1]):
					new = new.replace(x[0], x[1]) # whole-genome recoding
				elif len(x[0]) >= len(x[1]):
					x[1] == x[1] + '-' * (len(x[0]) - len(x[1]))
					new = new.replace(x[0], x[1]) # whole-genome recoding
					logging.warning('Genome modification involved the deletion of nucleotides and we proceeded as instructed.')
				else:
					logging.warning('Genome modification involves the insertion of nucleotides and we won\'t proceed as instructed.')
					raise NotImplementedError

		full_seqs[replicon] = Seq.Seq(new)

	# copy new sequences back
	for contig in contigs:
		contig.seq = full_seqs[contig.id]

	# If no tu_frame is provided generate a new TU frame where each mRNA gets its own TU
	#using_tus = tu_frame is not None
	#if not using_tus:
		#tu_frame = pandas.DataFrame(columns = ['genes'])
		#tu_frame = []
		#for contig in gb_file:
			#tu_frame.append(pandas.DataFrame.from_dict({
				#'TU_' + feature.qualifiers['locus_tag'][0]: {
					##'start': int(feature.location.start),
					##'stop': int(feature.location.end),
					#'replicon': contig.id,
					#'genes': dict(feature.qualifiers)['locus_tag'],
					#'start': ','.join([ str(x.start) for x in feature.location.parts ]),
					#'stop': ','.join([ str(x.end) for x in feature.location.parts ]),
					#'strand': "+" if feature.strand == 1 else "-",
					#} for feature in contig.features if (feature.type in element_types and feature.qualifiers.get('pseudo') is None)
				#}, orient = 'index'))
		#tu_frame = pandas.concat(tu_frame, axis = 0)

	# Create transcription reactions for each TU and DNA sequence.
	# RNA_products will be added so no need to update now
	for tu_id in tqdm.tqdm(tu_frame.index, 'Adding Transcriptional Units into the ME-model...', bar_format = bar_format):
		if any(x in tu_frame.genes[tu_id].split(',') for x in genes_to_add):
			start = tu_frame.start[tu_id]
			stop = tu_frame.stop[tu_id]
			strand = 1 if tu_frame.strand[tu_id] == '+' else -1
			organelle = tu_frame.organelle[tu_id]

			if len(start.split(',')) > 1:
				locations = []
				for start, stop in zip(start.split(','), stop.split(',')):
					locations.append(SeqFeature.FeatureLocation(
						SeqFeature.ExactPosition(int(start)-1), SeqFeature.ExactPosition(int(stop)), strand = strand))

					# Simplified to this in Bipython 1.81. TODO: TEST
					#locations.append(SeqFeature.SimpleLocation(int(start)-1, int(stop), strand = strand))

				seq = SeqFeature.SeqFeature(SeqFeature.CompoundLocation(locations, 'join'))
			else:
				seq = SeqFeature.SeqFeature(SeqFeature.FeatureLocation(
					SeqFeature.ExactPosition(int(start)-1), SeqFeature.ExactPosition(int(stop)), strand = strand))

				# Simplified to this in Bipython 1.81. TODO: TEST
				#seq = SeqFeature.SeqFeature(SeqFeature.SimpleLocation(int(start)-1, int(stop)), strand = strand)

			#sequence = coralme.util.dogma.extract_sequence(
				#full_seqs[tu_frame.replicon[tu_id]],
				#tu_frame.start[tu_id],
				#tu_frame.stop[tu_id],
				#tu_frame.strand[tu_id],
				#)

			seq = seq.extract(full_seqs[tu_frame.replicon[tu_id]]).ungap()
			if len(seq) == 0:
				logging.warning('The knockouts dictionary instructed to completely delete \'{:s}\' from the ME-model.'.format(tu_id))
			else:
				add_transcription_reaction(me_model, tu_id, set(), str(seq), organelle, update = False)

	# Dictionary of tRNA locus ID to the model.metabolite object
	trna_aa = {}

	# Dictionary of tRNA locus ID to amino acid, per organelle type
	aa2trna = {
		'c' : {}, # prokaryotes and eukaryotes
		'm' : {}, # mitochondria
		'h' : {}, # plastids
		}

	transl_tables = {
		'c' : set(), # prokaryotes and eukaryotes
		'm' : set(), # mitochondria
		'h' : set(), # plastids
		}

	# Set of start and stop codons
	start_codons = set()
	stop_codons = set()

	# Codon usage
	from collections import Counter
	codon_usage = Counter()

	# Associate each feature (RNA_product) with a TU and add translation reactions and demands
	for contig in contigs:
		for feature in tqdm.tqdm(contig.features, 'Adding features from contig {:s} into the ME-model...'.format(contig.id), bar_format = bar_format):
			# Find organelle in source
			if feature.type == 'source':
				organelle = feature.qualifiers.get('organelle', [None])[0]
				continue

			# Optionally add pseudo genes into the ME-model
			if not me_model.global_info['include_pseudo_genes'] and 'pseudo' in feature.qualifiers:
				continue

			# Add only features based on their type
			if feature.type not in feature_types:
				continue

			# Skip feature if it is not a gene used in the ME-model reconstruction
			filter1 = feature.qualifiers['locus_tag'][0] in knockouts
			filter2 = feature.qualifiers['locus_tag'][0] not in genes_to_add
			if filter1 or filter2:
				continue

			# Assign values for all important gene attributes
			bnum = feature.qualifiers['locus_tag'][0]
			# old code cannot consider if genes are split
			#left_pos = int(feature.location.start)
			#right_pos = int(feature.location.end)
			left_pos = ','.join([ str(x.start) for x in feature.location.parts ])
			right_pos = ','.join([ str(x.end) for x in feature.location.parts ])
			rna_type = 'mRNA' if feature.type == 'CDS' else feature.type
			strand = '+' if feature.strand == 1 else '-'
			# old code uses a cannon to hit a nail
			#seq = coralme.util.dogma.extract_sequence(full_seqs[contig.id], left_pos, right_pos, strand)

			seq = feature.extract(contig).seq.ungap() # using Biopython is better
			if len(seq) == 0:
				logging.warning('The genomic modification deleted \'{:s}\' from the ME-model that is not present in the knockouts list.'.format(bnum))
				continue

			# old code uses a dictionary setting the frameshifts.
			# the genbank already include frameshifts in the location of features
			# the genbank also sets the strand in the location; no need to reverse_transcribe()
			## Add gene metabolites and apply frameshift mutations----
			#frameshift_string = frameshift_dict.get(bnum)
			#if len(seq) % 3 != 0 and frameshift_string:
				#print('Applying frameshift on {:s}'.format(bnum))
				#seq = coralme.util.dogma.return_frameshift_sequence(full_seq, frameshift_string)
				#if strand == '-':
					#seq = coralme.util.dogma.reverse_transcribe(seq)

			# Add TranscribedGene metabolite
			create_transcribed_gene(me_model, bnum, rna_type, str(seq), left_pos, right_pos, strand)

			# Add translation reaction for mRNA
			if rna_type == 'mRNA' and len(seq) % 3 == 0: # if the genomic modification is not paired correctly with the knockouts list
				# Add the translation table
				prot = feature.qualifiers.get('translation', [''])[0]
				transl_table = feature.qualifiers.get('transl_table', ['1'])[0]
				add_translation_reaction(me_model, bnum, dna_sequence = str(seq), prot_sequence = str(prot), organelle = organelle, transl_table = int(transl_table), update = False)

				# Add the start codon to the start_codons set
				start_codons.add(str(seq[:3]).replace('T', 'U'))
				# Add the stop codon to the stop_codons sets
				stop_codons.add(str(seq[-3:]).replace('T', 'U'))

				# Add the translation table (eukaryotes)
				if organelle is None:
					transl_tables['c'].add(int(transl_table))
					if me_model.global_info['domain'].lower() not in ['prokaryote', 'bacteria']:
						logging.warning('Contig \'{:s}\' does not report an organelle type.'.format(contig.id))
				elif organelle.lower() in ['mitochondria', 'mitochondrion']:
					transl_tables['m'].add(int(transl_table))
				elif organelle.lower() in ['chloroplast', 'plastid']:
					transl_tables['h'].add(int(transl_table))
				else:
					continue

				# Add the codon usage
				codons = [ str(seq[pos:pos+3]) for pos in range(0, len(seq), 3) ]
				codon_usage.update(Counter(codons))

			me_model.global_info['transl_tables'] = transl_tables
			me_model.global_info['start_codons'] = start_codons
			me_model.global_info['stop_codons'] = stop_codons
			me_model.global_info['codon_usage'] = codon_usage

			# Create dict to use for adding tRNAChargingReactions later
			# tRNA_aa = {'tRNA':'amino_acid'}
			msg = 'From tRNA misacylation dictionary, make sure a MetabolicReaction to convert a {:s}-tRNA({:s}) into a {:s}-tRNA({:s}) is present in the ME-model.'
			if rna_type == 'tRNA':
				aa = feature.qualifiers['product'][0].split('-')[1]

				# misacylation of glutamate/aspartate occurs in archaea, Gram-positive eubacteria, mitochondria, and chloroplasts
				if aa in trna_misacylation.keys():
					# misacylation only in mitochondria and chloroplasts
					filter1a = me_model.global_info['domain'].lower() in ['eukarya', 'eukaryote']
					filter1b = str(organelle).lower() in ['mitochondria', 'mitochondrion', 'chloroplast', 'plastid']
					# misacylation in the cytoplasm of Gram-positive eubacteria (and other bacteria such as cyanobacteria)
					filter2 = me_model.global_info['domain'].lower() in ['bacteria', 'prokaryote']

					if filter1a and filter1b or filter2:
						trna_aa[bnum] = trna_misacylation[aa]
						logging.warning(msg.format(trna_misacylation[aa], aa, aa, aa))
					else:
						# misacylation is not valid in the compartment x domain
						trna_aa[bnum] = aa
				else:
					trna_aa[bnum] = aa

				#aa2trna[bnum] = aa # original tRNA<->Amino acid association to be used later in trna_to_codon

				if organelle is None:
					aa2trna['c'][bnum] = aa
				elif organelle.lower() in ['mitochondria', 'mitochondrion']:
					aa2trna['m'][bnum] = aa
				elif organelle.lower() in ['chloroplast', 'plastid']:
					aa2trna['h'][bnum] = aa
				#old code
				#trna_aa[bnum] = feature.qualifiers["product"][0].split('-')[1]

			trna_aa = { k:v.replace('fMet', 'Met') for k,v in trna_aa.items() }
			me_model.global_info['trna_to_aa'] = trna_aa

			## Associate the TranscribedGene to TU(s)
			# old code does not consider that a gene can start at the "end" of the genome and finish at the "start" of it
			#parent_tu = tu_frame[(tu_frame.start - 1 <= left_pos) & (tu_frame.stop >= right_pos) & (tu_frame.strand == strand)].index
			parent_tu = tu_frame[[ True if bnum in x else False for x in tu_frame.genes.values ]].index

			if len(parent_tu) == 0:
				tu_id = 'TU_' + bnum
				parent_tu = [tu_id]
				add_transcription_reaction(me_model, tu_id, set(), str(seq), organelle, update = False)
				logging.warning('No Trancriptional Unit found for {:s} {:s}. Created a dummy TU_{:s}.'.format(rna_type, bnum, bnum))

			for TU_id in parent_tu:
				me_model.process_data.get_by_id(TU_id).RNA_products.add('RNA_' + bnum)

	# DataFrame mapping tRNAs (list) and the encoded aminoacid (index), per organelle
	me_model.global_info['aa2trna'] = aa2trna

	for organelle, aa2trna_dct in aa2trna.items():
		aa2trna_dct = { k:v.capitalize().split('_')[0] if 'fMet' not in v else 'fMet' for k,v in aa2trna_dct.items() }
		aa2trna_dct = pandas.DataFrame(data = [aa2trna_dct.values(), aa2trna_dct.keys()]).T
		aa2trna_dct = aa2trna_dct.groupby(0).agg({1: lambda x: x.tolist()})
		if 'fMet' in aa2trna_dct.index:
			aa2trna_dct.loc['Met'] = aa2trna_dct.loc['fMet'] + aa2trna_dct.loc['Met']

		aa2trna[organelle] = aa2trna_dct

		# assign START tRNAs to every fMet-tRNA (Met-tRNA if not) and check if at least one tRNA was identified
		if 'fMet' in aa2trna_dct.index:
			if len(me_model.global_info['START_tRNA']) == 0:
				me_model.global_info['START_tRNA'] = list(aa2trna_dct.loc['fMet'])[0]
		if len(me_model.global_info['START_tRNA']) == 0:
			me_model.global_info['START_tRNA'] = list(aa2trna_dct.loc['Met'])[0]
		if len(me_model.global_info['START_tRNA']) == 0:
			logging.warning('Unable to identify at least one \'tRNA-Met\' or \'tRNA-fMet\' annotation from the \'Definition\' column in the organism-specific matrix.')

	# add charging tRNA reactions per organelle
	for organelle, transl_table in transl_tables.items():
		if len(transl_table) == 0:
			continue

		#codon_table = Bio.Data.CodonTable.generic_by_id[me_model.global_info.get('translation_table', 11)]
		#me_model.global_info['codon_table'] = codon_table
		codon_table = Bio.Data.CodonTable.generic_by_id[list(transl_table)[0]]

		dct = { k.replace('T', 'U'):SeqUtils.seq3(v) for k,v in codon_table.forward_table.items() if 'U' not in k }
		aa2codons = pandas.DataFrame(data = [dct.keys(), dct.values()]).T.groupby(1).agg({0: lambda x: x.tolist()})

		#if me_model.global_info.get('translation_table', None) is None:
			#me_model.global_info['translation_table'] = int(list(transl_table)[0]) if len(transl_table) == 1 else 11
			#logging.warning('Translation table was set to {:d} (See more https://www.ncbi.nlm.nih.gov/Taxonomy/Utils/wprintgc.cgi#SG{:d}).'.format(me_model.global_info['translation_table'], me_model.global_info['translation_table']))

		#if me_model.global_info['translation_table'] == 11:
		if list(transl_table)[0] == 11:
			aa2codons.loc['Sec'] = [['UGA']] # an internal UGA encodes selenocysteine

		df = pandas.concat([aa2codons, aa2trna[organelle]], axis = 1).dropna(how = 'any').explode(1)

		trna_to_codon = { k:v + ['START'] if k in me_model.global_info['START_tRNA'] else v for k,v in zip(df[1].values, df[0].values) }
		me_model.global_info['trna_to_codon'][organelle] = trna_to_codon

		convert_aa_codes_and_add_charging(me_model, trna_aa, trna_to_codon, organelle, verbose = verbose)

	if update:
		# Update all newly added reactions
		for r in me_model.reactions:
			if isinstance(r, coralme.core.reaction.TranscriptionReaction):
				r.update(verbose = verbose)
			if isinstance(r, coralme.core.reaction.TranslationReaction):
				r.update(verbose = verbose)

	return None

def update_genbank_reactions(me_model, verbose = True):
	for r in me_model.reactions:
		if isinstance(r, (coralme.core.reaction.TranscriptionReaction, coralme.core.reaction.TranslationReaction)):
			r.update(verbose = verbose)

	return None

def add_m_model_content(me_model, m_model, complex_metabolite_ids = []):
	"""
	Add metabolite and reaction attributes to me_model from m_model. Also
	creates StoichiometricData objects for each reaction in m_model, and adds
	reactions directly to me_model if they are exchanges or demands.

	Parameters
	----------
	me_model : :class:`coralme.core.model.MEModel`
		The MEModel object to which the content will be added

	m_model : :class:`coralme.core.model.Model`
		The m_model which will act as the source of metabolic content for
		MEModel

	complex_metabolite_ids : list
		List of complexes which are 'metabolites' in the m-model reaction
		matrix, but should be treated as complexes.

	"""
	for met in tqdm.tqdm(m_model.metabolites, 'Adding Metabolites from M-model into the ME-model...', bar_format = bar_format):
		if met.id in complex_metabolite_ids:
			new_met = coralme.core.component.Complex(met.id)
		elif met.id.startswith('RNA_'):
			#raise ValueError('Processed M-model should not contain RNAs ({:s})'.format(met.id))
			new_met = me_model.metabolites(met.id)
			logging.warning('Added TranscribedGene \'{:s}\'. It is highly probable the ME-model is not feasible.'.format(met.id))
		elif met.id.startswith('generic_tRNA'):
			new_met = coralme.core.component.GenerictRNA(met.id)
		else:
			new_met = coralme.core.component.Metabolite(met.id)

		new_met.name = met.name
		new_met.formula = met.formula
		new_met.compartment = met.compartment
		new_met.charge = met.charge
		new_met.annotation = met.annotation
		new_met.notes = met.notes
		me_model.add_metabolites(new_met)

	for reaction in tqdm.tqdm(m_model.reactions, 'Adding Reactions from M-model into the ME-model...', bar_format = bar_format):
		if reaction.id.startswith('BIOMASS_'):
			continue

		if reaction.id.startswith('EX_') or reaction.id.startswith('DM_') or reaction.id.startswith('SK_'):
			new_reaction = coralme.core.reaction.MEReaction(reaction.id)
			me_model.add_reactions([new_reaction])
			new_reaction.lower_bound = reaction.lower_bound
			new_reaction.upper_bound = reaction.upper_bound
			for met, stoichiometry in reaction.metabolites.items():
				new_reaction.add_metabolites({ me_model.metabolites.get_by_id(met.id): stoichiometry })
		else:
			reaction_data = coralme.core.processdata.StoichiometricData(reaction.id, me_model)
			reaction_data.lower_bound = reaction.lower_bound
			reaction_data.upper_bound = reaction.upper_bound
			reaction_data._stoichiometry = { k.id:v for k,v in reaction.metabolites.items() }

	return None

def add_dummy_reactions(me_model, update = True):
	"""
	Add all reactions necessary to produce a dummy reaction catalyzed by
	'CPLX_dummy'.

	Parameters
	----------
	me_model : :class:`coralme.core.model.MEModel`
		The MEModel object to which the content will be added

	dna_seq : str
		DNA sequence of dummy gene. Should be representative of the average
		codon composition, amino acid composition, length of a gene in the
		organism being modeled

	update : bool
		If True, run update functions on all transcription, translation,
		complex formation, and metabolic reactions added when constructing
		dummy reactions.

	"""
	stop_codons = me_model.global_info['stop_codons']
	stop_codons = [ x.replace('U', 'T') for x in stop_codons ]

	df_codons = pandas.DataFrame(data = me_model.global_info['codon_usage'].values(), index = me_model.global_info['codon_usage'].keys())
	df_codons['per_1000'] = df_codons / df_codons.sum() * 1000

	# protein sequence based on codon usage
	seq = 'ATG'
	for codon, row in df_codons.iterrows():
	#     if row.amino_acid == 'Stop':
		if codon in stop_codons:
			continue
		seq += codon * int(row.per_1000 // 3)  # want roughly 300 aa
	# get the most used stop codon; old code
	# seq += df_codons[df_codons.amino_acid == 'Stop'].sort_values('per_1000').index[-1]
	seq += df_codons[df_codons.index.isin(stop_codons)].sort_values('per_1000').index[-1]

	dummy = coralme.core.processdata.StoichiometricData(me_model.global_info['dummy_rxn_id'], me_model)
	dummy.lower_bound = 0
	dummy.upper_bound = 1000
	dummy._stoichiometry = {'CPLX_dummy': -1}

	create_transcribed_gene(me_model, 'dummy', 'mRNA', seq)
	add_transcription_reaction(me_model, 'RNA_dummy', {'dummy'}, seq)
	me_model.add_metabolites(coralme.core.component.TranslatedGene('protein_' + 'dummy'))
	add_translation_reaction(me_model, 'dummy', dna_sequence = seq, update = update)

	try:
		complex_data = coralme.core.processdata.ComplexData('CPLX_dummy', me_model)
	except ValueError:
		logging.warning('Complex \'CPLX_dummy\' already present in the ME-model.')
		complex_data = me_model.process_data.get_by_id('CPLX_dummy')
	complex_data.stoichiometry = {'protein_dummy': 1}

	if update:
		complex_data.create_complex_formation()

	return None

def add_complex_to_model(me_model, complex_id, complex_stoichiometry, complex_modifications = None):
	"""
	Adds ComplexData to the model for a given complex.

	Parameters
	----------
	me_model : :class:`coralme.core.model.MEModel`

	complex_id : str
		ID of the complex and thus the model ComplexData

	complex_stoichiometry : dict
		{complex_id: {protein_<locus_tag>: stoichiometry}}

	complex_modifications : dict
		{subreaction_id: stoichiometry}

	"""

	if not complex_modifications:
		complex_modifications = {}

	complex_data = coralme.core.processdata.ComplexData(complex_id, me_model)
	# must add update stoichiometry one by one since it is a defaultdict
	for metabolite, value in complex_stoichiometry.items():
		complex_data.stoichiometry[metabolite] += value
	for modification, value in complex_modifications.items():
		complex_data.subreactions[modification] = value

	return None

def add_subreaction_data(me_model, modification_id, modification_stoichiometry, modification_enzyme = None, verbose = True):
	"""
	Creates a SubreactionData object for each modification defined by the
	function inputs.

	It's assumed every complex modification occurs spontaneously, unless a
	modification_enzyme argument is passed.

	If a modification uses an enzyme this can be updated after the
	SubreactionData object is already created

	Parameters
	----------
		me_model : :class:`coralme.core.model.MEModel`

	"""

	if modification_id in me_model.process_data:
		#if verbose:
		logging.warning('SubReaction \'{:s}\' is already in the ME-model and its stoichiometry was modified on your request.'.format(modification_id))
		me_model.process_data.get_by_id(modification_id).stoichiometry = modification_stoichiometry
		#else:
			#pass
	else:
		modification_data = coralme.core.processdata.SubreactionData(modification_id, me_model)
		modification_data.stoichiometry = modification_stoichiometry
		modification_data.enzyme = modification_enzyme
		try:
			modification_data._element_contribution = modification_data.calculate_element_contribution()
		except:
			modification_data._element_contribution = {}

	return None

def add_model_complexes(me_model, complex_stoichiometry_dict, complex_modification_dict, verbose = True):
	"""
	Construct ComplexData for complexes into MEModel from its subunit
	stoichiometry, and a dictionary of its modification metabolites.

	It is assumed that each modification adds one equivalent of the
	modification metabolite. Multiple

	Intended to be used as a function for large-scale complex addition.

	For adding individual ComplexData objects, use add_complex_to_model

	Parameters
	----------
	me_model : :class:`coralme.core.model.MEModel`

	complex_stoichiometry_dict : dict
		{unmodified_complex_id: {protein_<locus_tag>: stoichiometry}}

	complex_modification_dict : dict
		{modified_complex_id:{
			core_enzyme: unmodified_complex_id,
			'modifications: {
				mod_metabolite: stoichiometry
				}
			}
		}

	"""
	for complex_id, stoichiometry in complex_stoichiometry_dict.items():
		add_complex_to_model(me_model, complex_id, stoichiometry, {})

	for modified_complex_id, info in complex_modification_dict.items():
		modification_dict = {}
		for metabolite, number in info['modifications'].items():
			if me_model.process_data.has_id('mod_' + metabolite):
				pass
			else:
				modification_id = 'mod_' + metabolite
				# add modification as a SubReaction
				add_subreaction_data(me_model, modification_id, {metabolite: -1}, verbose = verbose)
				# stoichiometry of modification determined in modification_data.stoichiometry
				modification_dict[modification_id] = abs(number)

		core_enzyme = complex_modification_dict[modified_complex_id]['core_enzyme']
		stoichiometry = complex_stoichiometry_dict[core_enzyme]

		add_complex_to_model(me_model, modified_complex_id, stoichiometry, complex_modifications = modification_dict)

	return None

def add_metabolic_reaction_to_model(me_model, stoichiometric_data_id, directionality, complex_id = None, spontaneous = False, update = False, keff = 65.):
	"""
	Creates and add a MetabolicReaction to a MEModel.

	Parameters
	----------
	me_model : :class:`coralme.core.model.MEModel`
		MEModel that the MetabolicReaction will be added to

	stoichiometric_data_id : str
		ID of the StoichiometricData for the reaction being added

	directionality : str
		- Forward: Add reaction that occurs in the forward direction
		- Reverse: Add reaction that occurs in the reverse direction

	complex_id : str or None
		ID of the ComplexData for the enzyme that catalyze the reaction
		being added.

	spontaneous : bool
		- If True and complex_id='' add reaction as spontaneous reaction
		- If False and complex_id='' add reaction as orphan (CPLX_dummy
		  catalyzed)

	"""
	# Get stoichiometric data for reaction being added

	#print(stoichiometric_data_id)

	try:
		stoichiometric_data = me_model.process_data.get_by_id(stoichiometric_data_id)
	except KeyError:
		raise Exception('StoichiometricData for \'{:s}\' has not been added to ME-model.'.format(stoichiometric_data_id))

	# Get complex data and id based on arguments passed into function
	if isinstance(complex_id, str) and complex_id != 'dummy_MONOMER':
		complex_data = me_model.process_data.get_by_id(complex_id)

	#elif complex_id is None and spontaneous is True:
	elif (complex_id == 'dummy_MONOMER' or complex_id is None) and spontaneous is True:
		complex_id = 'SPONT'
		complex_data = None
	#elif complex_id is None and spontaneous is False:
	elif (complex_id == 'dummy_MONOMER' or complex_id is None) and spontaneous is False:
		complex_id = 'CPLX_dummy'
		try:
			complex_data = me_model.process_data.get_by_id(complex_id)
		except KeyError:
			raise Exception('\'CPLX_dummy\' must be added to complex data to add orphan reactions.')
	else:
		raise ValueError('Complex id \'{:s}\' must be a string or None.'.format(str(complex_id)))

	if directionality.lower() == 'forward':
		direction = '_FWD_'
		reverse_flag = False
	elif directionality.lower() == 'reverse':
		direction = '_REV_'
		reverse_flag = True
	else:
		raise NameError('Reaction direction must be \'forward\' or \'reverse\'.')

	r = coralme.core.reaction.MetabolicReaction(''.join([stoichiometric_data_id, direction, complex_id]))
	me_model.add_reactions([r])
	r.keff = keff
	r.stoichiometric_data = stoichiometric_data
	r.reverse = reverse_flag

	if complex_data is not None:
		r.complex_data = complex_data
	if update:
		r.update(verbose = True)

	return None

def add_reactions_from_stoichiometric_data(
	me_model, rxn_to_cplx_dict,
	rxn_info_frame = pandas.DataFrame(), is_spontaneous = [],
	update = False, keff = 65.):
	"""
	Creates and adds MetabolicReaction for all StoichiometricData in model.

	Intended for use when adding all reactions from stoichiometric data for the
	first time.

	For adding an individual reaction use add_metabolic_reaction_to_model()

	Parameters
	----------
	me_model : :class:`coralme.core.model.MEModel`
		MEModel that the MetabolicReaction will be added to

	rxn_to_cplx_dict : dict
		{StoichiometricData.id: catalytic_enzyme_id}

	rxn_info_frame: :class:`pandas.Dataframe`
		Contains the ids, names and reversibility for each reaction in the
		metabolic reaction matrix as well as whether the reaction is
		spontaneous
	"""
	for reaction_data in tqdm.tqdm(list(me_model.stoichiometric_data), 'Processing StoichiometricData in ME-model...', bar_format = bar_format):
		#try:
			#spontaneous_flag = rxn_info_frame.is_spontaneous[reaction_data.id]
		#except KeyError:
			#spontaneous_flag = False
			#logging.warning('Reaction \'{:s}\' not in rxn_info_frame assumed nonspontaneous.'.format(reaction_data.id))

		#if spontaneous_flag == 1:
			#spontaneous = True
		#elif spontaneous_flag == 0:
			#spontaneous = False
		#else:
			#raise Exception('is_spontaneous must be \'True\' or \'False\'.')

		if reaction_data.id in is_spontaneous:
			spontaneous = True
		else:
			spontaneous = False

		# Reactions can be catalyzed by multiple isozymes so retrieve list of
		# complexes that catalyze the reaction
		complexes_list = rxn_to_cplx_dict.get(reaction_data.id, [None])

		# Add metabolic reactions for each isozyme
		for complex_id in complexes_list:

			directionality_list = []
			if reaction_data.lower_bound < 0:
				directionality_list.append('reverse')
			if reaction_data.upper_bound > 0:
				directionality_list.append('forward')
			if reaction_data.upper_bound == 0 and reaction_data.lower_bound == 0:
				directionality_list.append('forward')
				logging.warning('Reaction \'{:s}\' cannot carry flux. Check if it is the correct behavior.'.format(reaction_data.id))

			for directionality in directionality_list:
				add_metabolic_reaction_to_model(
					me_model,
					reaction_data.id,
					directionality,
					complex_id = complex_id,
					spontaneous = spontaneous,
					update = update,
					keff = keff
					)

	return None
