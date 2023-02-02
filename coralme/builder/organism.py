#!/usr/bin/python3
import os
import re
import random
import io

from collections import defaultdict

import Bio
import cobra
import pandas

from coralme.builder import dictionaries

import warnings
try:
	warnings.simplefilter(action = 'ignore', category = Bio.BiopythonWarning)
except:
	warnings.warn("This biopython version does not allow for correct warning handling. Biopython >=1.80 is suggested.")

class Organism(object):
    """Organism class for storing information about an organism

    This class acts as a database containing all necessary information
    to reconstruct a ME-model. It is used to retrieve and store
    information of the main (org) and the reference (ref) organisms.
    Information in Organism is read and manipulated by methods in
    the MEBuilder class.

    Parameters
    ----------
    org : str
        Identifier of the main organism. Has to be the same as the
        containing folder name.

    is_reference : bool
        If True, process as reference organism.

    create_minimal_files : bool
        False to read minimal files from folder, True to generate minimal
        files from genome.gb. Minimal files genes.txt, proteins.txt,
        RNAs.txt, and TUs.txt can be generated from the genbank file,
        though some information might be lost. Set this parameter to
        True if minimal files are not available.
    """

    def __init__(self, config, is_reference):
        if is_reference:
            if bool(config.get('dev_reference', False)) and bool(config.get('user_reference', False)):
                self.id = 'iJL1678b'
            elif bool(config.get('dev_reference', False)) and bool(config.get('user_reference', False)):
                self.id = config['user_reference']
            elif bool(config.get('dev_reference', False)) and bool(config.get('user_reference', False)):
                print('The \'dev_reference\' and \'user-reference\' options are mutually exclusive.')
                self.id = 'iJL1678b'
            else:
                self.id = 'iJL1678b'
        else:
            self.id = config['model_id']

        self.is_reference = is_reference
        self.create_minimal_files = bool(config.get('create_files', True))
        self.curation_notes = defaultdict(list)
        self.config = config
        self.locus_tag = config.get('locus_tag','locus_tag')

        data = \
            'code,interpretation,gram\n' \
            'CCI-CW-BAC-POS-GP,Cell_Wall,pos\n' \
            'CCI-OUTER-MEM-GN,Outer_Membrane,neg\n' \
            'CCI-PM-BAC-NEG-GN,Inner_Membrane,neg\n' \
            'CCI-PM-BAC-POS-GP,Plasma_Membrane,pos\n' \
            'CCO-MEMBRANE,Membrane,'

        self.location_interpreter = pandas.read_csv(io.StringIO(data), index_col=0)

        self.get_organism()

    @property
    def directory(self):
        if self.is_reference and self.id == 'iJL1678b':
            try:
                from importlib.resources import files
            except ImportError:
                from importlib_resources import files
            return str(files("coralme") / self.id) + "-ME/building_data/"
        else:
            return self.config.get('out_directory', self.id) + "/building_data/"
        #return self.id + "/building_data/"

    @property
    def blast_directory(self):
        if self.is_reference:
            pass
        else:
            return self.config.get('out_directory', self.id) + "/blast_files_and_results/"

    @property
    def _complexes_df(self):
        filename = self.directory + "protein_complexes.txt"
        if os.path.isfile(filename):
            return pandas.read_csv(
                filename, index_col=0, sep="\t"
            )
        else:
            return self.generate_complexes_df()

    @property
    def _protein_mod(self):
        filename = self.directory + "protein_modification.txt"
        if os.path.isfile(filename):
            return pandas.read_csv(
                filename, index_col=0, sep="\t"
            )
        else:
            return pandas.DataFrame.from_dict(
                {
                    "Modified_enzyme": {},
                    "Core_enzyme": {},
                    "Modifications": {},
                    "Source": {},
                }
            ).set_index("Modified_enzyme")

    @property
    def _gene_sequences(self):
        filename = self.config.get('biocyc.seqs', self.directory + "sequences.fasta")
        if os.path.isfile(filename):
            d = {}
            for i in Bio.SeqIO.parse(filename,'fasta'):
                for g in i.id.split('|'):
                    d[g] = i
            return d
        return {}

    @property
    def _manual_complexes(self):
        filename = self.directory + "protein_corrections.csv"
        if os.path.isfile(filename):
            return pandas.read_csv(filename, index_col=0).fillna("")
        else:
            self.curation_notes['org._manual_complexes'].append({
                'msg':"No manual complexes file, creating one",
                'importance':'low',
                'to_do':'Fill manual_complexes.csv'})
            df = pandas.DataFrame.from_dict(
                {"complex_id": {}, "name": {}, "genes": {}, "mod": {}, "replace": {}}
            ).set_index("complex_id")
            df.to_csv(filename)
            return df

    @property
    def _TU_df(self):
        filename = self.config.get('df_TranscriptionalUnits', self.directory + "TUs_from_biocyc.txt")
        if os.path.isfile(filename) and not self.config.get('overwrite', True):
            return pandas.read_csv(filename, index_col = 0, sep = "\t")
        else:
            return self.get_TU_df()

    @property
    def _sigmas(self):
        filename = self.directory + "sigma_factors.csv"
        if os.path.isfile(filename):
            return pandas.read_csv(
                filename, index_col=0, sep=","
            )
        else:
            return self.get_sigma_factors()

    @property
    def _rpod(self):
        return self.get_rpod()

    @property
    def _m_to_me_mets(self):
        filename = self.directory + "m_to_me_mets.csv"
        if os.path.isfile(filename):
            return pandas.read_csv(filename, index_col=0)
        else:
            self.curation_notes['org._m_to_me_mets'].append({
                'msg':"No m_to_me_mets.csv file found",
                'importance':'low',
                'to_do':'Fill m_to_me_mets.csv'})
            df = pandas.DataFrame.from_dict({"m_name": {}, "me_name": {}})
            df.set_index("m_name")
            df.to_csv(filename)
            return df

    @property
    def _rna_degradosome(self):
        filename = self.directory + "rna_degradosome.csv"
        if os.path.isfile(filename):
            d = (
                pandas.read_csv(filename, index_col=0, sep="\t")
                .fillna("").T
                .to_dict()
            )
            for k, v in d.items():
                d[k] = {}
                if v['enzymes']:
                    d[k]['enzymes'] = v['enzymes'].split(",")
                else:
                    d[k]['enzymes'] = []
        else:
            self.curation_notes['org._rna_degradosome'].append({
                'msg':"No rna_degradosome.csv file found",
                'importance':'low',
                'to_do':'Fill rna_degradosome.csv'})
            d = {'rna_degradosome':{'enzymes':[]}}
            df_save = pandas.DataFrame.from_dict(d).T
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzymes"] = ",".join(row["enzymes"])
            df_save.index.name = "name"
            df_save.to_csv(filename, sep="\t")
        return d

    @property
    def _ribosome_stoich(self):
        filename = self.directory + "ribosomal_proteins.csv"
        if os.path.isfile(filename):
            df = pandas.read_csv(filename, sep="\t", index_col=0).fillna('')
            return self.create_ribosome_stoich(df)
        else:
            self.curation_notes['org._ribosomal_proteins'].append({
                'msg':"No ribosomal_proteins.csv file found",
                'importance':'low',
                'to_do':'Fill ribosomal_proteins.csv'})
            return self.write_ribosome_stoich(filename)

    @property
    def _ribosome_subreactions(self):
        filename = self.directory + "ribosome_subreactions.csv"
        if os.path.isfile(filename):
            d = pandas.read_csv(filename, sep="\t", index_col=0).fillna("").T.to_dict()
            for r, row in d.items():
                d[r]["stoich"] = self.str_to_dict(row["stoich"])
        else:
            self.curation_notes['org._ribosome_subreactions'].append({
                'msg':"No ribosome_subreactions.csv file found",
                'importance':'low',
                'to_do':'Fill ribosome_subreactions.csv'})
            df = pandas.DataFrame.from_dict(dictionaries.ribosome_subreactions).T
            df_save = df.copy()
            for r, row in df_save.iterrows():
                df_save.loc[r, "stoich"] = self.dict_to_str(row["stoich"])
            df_save.to_csv(filename, sep="\t")
            d = df.T.to_dict()
        return d

    @property
    def _generic_dict(self):
        filename = self.directory + "generic_dict.csv"
        if os.path.isfile(filename):
            d = (
                pandas.read_csv(filename, index_col=0, sep="\t")
                .fillna("").T
                .to_dict()
            )
            for k, v in d.items():
                d[k] = {}
                if v['enzymes']:
                    d[k]['enzymes'] = v['enzymes'].split(",")
                else:
                    d[k]['enzymes'] = []
        else:
            self.curation_notes['org._generic_dict'].append({
                'msg':"No generic_dict.csv file found",
                'importance':'low',
                'to_do':'Fill generic_dict.csv'})
            d = dictionaries.generics.copy()
            df_save = pandas.DataFrame.from_dict(d).T
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzymes"] = ",".join(row["enzymes"])
            df_save.index.name = "generic_component"
            df_save.to_csv(filename, sep="\t")
        return d

    @property
    def _rrna_modifications(self):
        filename = self.directory + "rrna_modifications.csv"
        if os.path.isfile(filename):
            d = pandas.read_csv(filename, sep="\t", index_col=0).fillna("").T.to_dict()
            for k, v in d.items():
                v["metabolites"] = self.str_to_dict(v["metabolites"])
        else:
            self.curation_notes['org._rrna_modifications'].append({
                'msg':"No rrna_modifications.csv file found",
                'importance':'low',
                'to_do':'Fill rrna_modifications.csv'})
            df = pandas.DataFrame.from_dict(dictionaries.rrna_modifications).T
            df_save = df.copy()
            for r, row in df_save.iterrows():
                df_save.loc[r, "metabolites"] = self.dict_to_str(row["metabolites"])
            df_save.to_csv(filename, sep="\t")
            d = df.T.to_dict()
        return d

    @property
    def _amino_acid_trna_synthetase(self):
        filename = self.directory + "amino_acid_trna_synthetase.csv"
        if os.path.isfile(filename):
            d = (
                pandas.read_csv(filename, index_col=0, sep="\t")
                .fillna("")["enzyme"]
                .to_dict()
            )
        else:
            self.curation_notes['org._amino_acid_trna_synthetase'].append({
                'msg':"No amino_acid_trna_synthetase.csv file found",
                'importance':'low',
                'to_do':'Fill amino_acid_trna_synthetase.csv'})
            d = dictionaries.amino_acid_trna_synthetase.copy()
            pandas.DataFrame.from_dict({"enzyme": d}).to_csv(filename, sep="\t")
        return d

    @property
    def _peptide_release_factors(self):
        filename = self.directory + "peptide_release_factors.csv"
        if os.path.isfile(filename):
            d = (
                pandas.read_csv(filename, index_col=0, sep="\t")
                .fillna("").T
                .to_dict()
            )
            for k, v in d.items():
                d[k] = {}
                if v['enzyme']:
                    d[k]['enzyme'] = v['enzyme']
                else:
                    d[k]['enzyme'] = ''
        else:
            self.curation_notes['org._peptide_release_factors'].append({
                'msg':"No peptide_release_factors.csv file found",
                'importance':'low',
                'to_do':'Fill peptide_release_factors.csv'})
            d = dictionaries.translation_stop_dict.copy()
            df_save = pandas.DataFrame.from_dict(d).T
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzyme"] = row["enzyme"]
            df_save.index.name = "codon"
            df_save.to_csv(filename, sep="\t")
        return d

    @property
    def _initiation_subreactions(self):
        filename = self.directory + "initiation_subreactions.csv"
        if os.path.isfile(filename):
            d = pandas.read_csv(filename, index_col=0, sep="\t").T.fillna("").to_dict()
            for k, v in d.items():
                v["enzymes"] = v["enzymes"].split(",")
                if "" in v["enzymes"]:
                    v["enzymes"].remove("")
                v["stoich"] = self.str_to_dict(v["stoich"])
                v["element_contribution"] = self.str_to_dict(v["element_contribution"])
        else:
            self.curation_notes['org._initiation_subreactions'].append({
                'msg':"No initiation_subreactions.csv file found",
                'importance':'low',
                'to_do':'Fill initiation_subreactions.csv'})
            df = pandas.DataFrame.from_dict(dictionaries.initiation_subreactions).T
            df_save = df.copy()
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzymes"] = ",".join(row["enzymes"])
                df_save.loc[r, "stoich"] = self.dict_to_str(row["stoich"])
                df_save.loc[r, "element_contribution"] = self.dict_to_str(
                    row["element_contribution"]
                )
            df_save.to_csv(filename, sep="\t")
            d = df.T.to_dict()
        return d

    @property
    def _elongation_subreactions(self):
        filename = self.directory + "elongation_subreactions.csv"
        if os.path.isfile(filename):
            d = pandas.read_csv(filename, index_col=0, sep="\t").T.fillna("").to_dict()
            for k, v in d.items():
                v["enzymes"] = v["enzymes"].split(",")
                if "" in v["enzymes"]:
                    v["enzymes"].remove("")
                v["stoich"] = self.str_to_dict(v["stoich"])
        else:
            self.curation_notes['org._elongation_subreactions'].append({
                'msg':"No elongation_subreactions.csv file found",
                'importance':'low',
                'to_do':'Fill elongation_subreactions.csv'})
            df = pandas.DataFrame.from_dict(dictionaries.elongation_subreactions).T
            df_save = df.copy()
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzymes"] = ",".join(row["enzymes"])
                df_save.loc[r, "stoich"] = self.dict_to_str(row["stoich"])
            df_save.to_csv(filename, sep="\t")
            d = df.T.to_dict()
        return d

    @property
    def _termination_subreactions(self):
        filename = self.directory + "termination_subreactions.csv"
        if os.path.isfile(filename):
            d = pandas.read_csv(filename, index_col=0, sep="\t").T.fillna("").to_dict()
            for k, v in d.items():
                v["enzymes"] = v["enzymes"].split(",")
                if "" in v["enzymes"]:
                    v["enzymes"].remove("")
                v["stoich"] = self.str_to_dict(v["stoich"])
                v["element_contribution"] = self.str_to_dict(v["element_contribution"])
        else:
            self.curation_notes['org._termination_subreactions'].append({
                'msg':"No termination_subreactions.csv file found",
                'importance':'low',
                'to_do':'Fill termination_subreactions.csv'})
            df = pandas.DataFrame.from_dict(dictionaries.termination_subreactions).T
            df[["element_contribution"]] = df[["element_contribution"]].applymap(
                lambda x: {} if pandas.isnull(x) else x
            )
            df_save = df.copy()
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzymes"] = ",".join(row["enzymes"])
                df_save.loc[r, "stoich"] = self.dict_to_str(row["stoich"])
                df_save.loc[r, "element_contribution"] = self.dict_to_str(
                    row["element_contribution"]
                )
            df_save.to_csv(filename, sep="\t")
            d = df.T.to_dict()
        return d

    @property
    def _special_trna_subreactions(self):
        filename = self.directory + "special_trna_subreactions.csv"
        if os.path.isfile(filename):
            d = pandas.read_csv(filename, index_col=0, sep="\t").T.fillna("").to_dict()
            for k, v in d.items():
                v["enzymes"] = v["enzymes"].split(",")
                if "" in v["enzymes"]:
                    v["enzymes"].remove("")
                v["stoich"] = self.str_to_dict(v["stoich"])
                v["element_contribution"] = self.str_to_dict(v["element_contribution"])
        else:
            self.curation_notes['org._special_trna_subreactions'].append({
                'msg':"No special_trna_subreactions.csv file found",
                'importance':'low',
                'to_do':'Fill special_trna_subreactions.csv'})
            df = pandas.DataFrame.from_dict(dictionaries.special_trna_subreactions).T
            df_save = df.copy()
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzymes"] = ",".join(row["enzymes"])
                df_save.loc[r, "stoich"] = self.dict_to_str(row["stoich"])
                df_save.loc[r, "element_contribution"] = self.dict_to_str(
                    row["element_contribution"]
                )
            df_save.to_csv(filename, sep="\t")
            d = df.T.to_dict()
        return d

    @property
    def _excision_machinery(self):
        filename = self.directory + "excision_machinery.csv"
        if os.path.isfile(filename):
            d = (
                pandas.read_csv(filename, index_col=0, sep="\t")
                .fillna("").T
                .to_dict()
            )
            for k, v in d.items():
                d[k] = {}
                if v['enzymes']:
                    d[k]['enzymes'] = v['enzymes'].split(",")
                else:
                    d[k]['enzymes'] = []
        else:
            self.curation_notes['org._excision_machinery'].append({
                'msg':"No excision_machinery.csv file found",
                'importance':'low',
                'to_do':'Fill excision_machinery.csv'})
            d = dictionaries.excision_machinery.copy()
            df_save = pandas.DataFrame.from_dict(d).T
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzymes"] = ",".join(row["enzymes"])
            df_save.index.name = "mechanism"
            df_save.to_csv(filename, sep="\t")
        return d

    @property
    def _special_modifications(self):
        filename = self.directory + "special_modifications.csv"
        if os.path.isfile(filename):
            d = pandas.read_csv(filename, index_col=0, sep="\t").T.fillna("").to_dict()
            for k, v in d.items():
                v["enzymes"] = v["enzymes"].split(",")
                if "" in v["enzymes"]:
                    v["enzymes"].remove("")
                v["stoich"] = self.str_to_dict(v["stoich"])
        else:
            self.curation_notes['org._special_modifications'].append({
                'msg':"No special_modifications.csv file found",
                'importance':'low',
                'to_do':'Fill special_modifications.csv'})
            df = pandas.DataFrame.from_dict(dictionaries.special_modifications).T
            df_save = df.copy()
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzymes"] = ",".join(row["enzymes"])
                df_save.loc[r, "stoich"] = self.dict_to_str(row["stoich"])
            df_save.to_csv(filename, sep="\t")
            d = df.T.to_dict()
        return d

    @property
    def _trna_modification(self):
        filename = self.directory + "trna_modification.csv"
        if os.path.isfile(filename):
            d = pandas.read_csv(filename, index_col=0, sep="\t").T.fillna("").to_dict()
            for k, v in d.items():
                v["enzymes"] = v["enzymes"].split(",")
                if "" in v["enzymes"]:
                    v["enzymes"].remove("")
                v["stoich"] = self.str_to_dict(v["stoich"])
                v["carriers"] = self.str_to_dict(v["carriers"])
        else:
            self.curation_notes['org._trna_modification'].append({
                'msg':"No trna_modification.csv file found",
                'importance':'low',
                'to_do':'Fill trna_modification.csv'})
            df = pandas.DataFrame.from_dict(dictionaries.trna_modification).T
            df[["carriers"]] = df[["carriers"]].applymap(
                lambda x: {} if pandas.isnull(x) else x
            )
            df_save = df.copy()
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzymes"] = ",".join(row["enzymes"])
                df_save.loc[r, "stoich"] = self.dict_to_str(row["stoich"])
                df_save.loc[r, "carriers"] = self.dict_to_str(row["carriers"])
            df_save.to_csv(filename, sep="\t")
            d = df.T.to_dict()
        return d

    @property
    def _trna_modification_targets(self):
        filename = self.directory + "post_transcriptional_modification_of_tRNA.csv"
        if os.path.isfile(filename):
            df = pandas.read_csv(filename, delimiter="\t")
        else:
            self.curation_notes['org._trna_modification_targets'].append({
                'msg':"No post_transcriptional_modification_of_tRNA.csv file found",
                'importance':'low',
                'to_do':'Fill post_transcriptional_modification_of_tRNA.csv'})
            df = pandas.DataFrame.from_dict(
                {"bnum": {}, "position": {}, "modification": {}})

            df.to_csv(filename, sep="\t")
        trna_mod_dict = {}
        for mod in df.iterrows():
            mod = mod[1]
            mod_loc = "%s_at_%s" % (mod["modification"], mod["position"])
            if mod["bnum"] not in trna_mod_dict:
                trna_mod_dict[mod["bnum"]] = {}
            trna_mod_dict[mod["bnum"]][mod_loc] = 1
        return trna_mod_dict

    @property
    def _folding_dict(self):
        filename = self.directory + "folding_dict.csv"
        if os.path.isfile(filename):
            d = (
                pandas.read_csv(filename, index_col=0, sep="\t")
                .fillna("").T
                .to_dict()
            )
            for k, v in d.items():
                d[k] = {}
                if v['enzymes']:
                    d[k]['enzymes'] = v['enzymes'].split(",")
                else:
                    d[k]['enzymes'] = []
        else:
            self.curation_notes['org._folding_dict'].append({
                'msg':"No folding_dict.csv file found",
                'importance':'low',
                'to_do':'Fill folding_dict.csv'})
            d = dictionaries.folding_dict.copy()
            df_save = pandas.DataFrame.from_dict(d).T
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzymes"] = ",".join(row["enzymes"])
            df_save.index.name = "mechanism"
            df_save.to_csv(filename, sep="\t")
        return d

    @property
    def _transcription_subreactions(self):
        filename = self.directory + "transcription_subreactions.csv"
        if os.path.isfile(filename):
            d = pandas.read_csv(filename, index_col=0, sep="\t").T.fillna("").to_dict()
            for k, v in d.items():
                v["enzymes"] = v["enzymes"].split(",")
                if "" in v["enzymes"]:
                    v["enzymes"].remove("")
                v["stoich"] = self.str_to_dict(v["stoich"])
        else:
            self.curation_notes['org._transcription_subreactions'].append({
                'msg':"No transcription_subreactions.csv file found",
                'importance':'low',
                'to_do':'Fill transcription_subreactions.csv'})
            df = pandas.DataFrame.from_dict(dictionaries.transcription_subreactions).T
            df_save = df.copy()
            for r, row in df_save.iterrows():
                df_save.loc[r, "enzymes"] = ",".join(row["enzymes"])
                df_save.loc[r, "stoich"] = self.dict_to_str(row["stoich"])
            df_save.to_csv(filename, sep="\t")
            d = df.T.to_dict()
        return d

    @property
    def _translocation_pathways(self):
        filename = self.directory + "translocation_pathways.csv"
        if os.path.isfile(filename):
            df = pandas.read_csv(filename, index_col=0, delimiter="\t").fillna("")
            return self.read_translocation_pathways(df)
        else:
            self.curation_notes['org._translocation_pathways'].append({
                'msg':"No translocation_pathways.csv file found",
                'importance':'low',
                'to_do':'Fill translocation_pathways.csv'})
            columns = [
                "keff",
                "length_dependent_energy",
                "stoichiometry",
                "enzyme",
                "length_dependent",
                "fixed_keff",
            ]
            df = pandas.DataFrame(columns=columns)
            df.index.name = 'pathway'
            df.to_csv(filename, sep="\t")
            return dict()

    @property
    def _protein_location(self):
        filename = self.directory + "peptide_compartment_and_pathways.csv"
        if os.path.isfile(filename):
            return pandas.read_csv(filename, index_col = 0, delimiter = "\t")
        else:
            self.curation_notes['org._protein_location'].append({
                'msg':"No peptide_compartment_and_pathways.csv file found",
                'importance':'low',
                'to_do':'Fill peptide_compartment_and_pathways.csv'})
            columns = [
                'Complex',
                'Complex_compartment',
                'Protein',
                'Protein_compartment',
                'translocase_pathway',
                ]
            pandas.DataFrame(columns = columns).set_index('Complex').to_csv(filename, sep = "\t")
            return self.get_protein_location()

    @property
    def _m_model(self):
        model = self.config['m-model-path']
        if model.endswith('.json'):
            return cobra.io.load_json_model(model)
        elif model.endswith('.xml'):
            return cobra.io.read_sbml_model(model)
        else:
            print('M-model input file must be json or xml format.')

    @property
    def rna_components(self):
        product_types = self.product_types
        return set(g for g,t in product_types.items() if 'RNA' in t)

    def get_organism(self):
        sep = " "*5
        print("Getting {}".format(self.id))
        if self.id != 'iJL1678b':
            print("Checking minimal necessary files")
            self.check_minimal_files()
        print("{} Loading M-model {}".format(sep, sep))
        self.m_model = self._m_model
        print("{} Checking M-model {}".format(sep, sep))
        self.check_m_model()
        print("{} Loading M to ME metabolites dictionary {}".format(sep, sep))
        self.m_to_me_mets = self._m_to_me_mets
        print("{} Loading genbank file {}".format(sep, sep))
        self.get_genbank_contigs()
        if self.create_minimal_files and not self.is_reference:
            print("{} Generating minimal files from genbank {}".format(sep, sep))
            self.generate_minimal_files()
        print("{} Loading gene dictionary {}".format(sep, sep))
        self.gene_dictionary = self.read_gene_dictionary()
        self.gene_sequences = self._gene_sequences
        print("{} Checking gene overlap {}".format(sep, sep))
        self.check_gene_overlap()
        print("{} Getting proteins from BioCyc {}".format(sep, sep))
        self.proteins_df = pandas.read_csv(
            self.config.get('biocyc.prots', self.directory + "proteins.txt"), index_col=0, sep="\t"
        )
        print("{} Getting RNAs from BioCyc {}".format(sep, sep))
        self.RNA_df = pandas.read_csv(
            self.config.get('biocyc.RNAs', self.directory + "RNAs.txt"), index_col=0, sep="\t"
        )
        print("{} Generating complexes dataframe {}".format(sep, sep))
        self.complexes_df = self._complexes_df
        print("{} Syncing files {}".format(sep, sep))
        self.sync_files()
        print('{} Completing genbank with provided files {}'.format(sep, sep))
        self.update_genbank_from_files()
        print("{} Updating genes and complexes from genbank {}".format(sep, sep))
        self.update_complexes_genes_with_genbank()

        print("{} Purging genes in M-model {}".format(sep,sep))
        self.purge_genes_in_model()

        print("{} Generating protein modifications dataframe {}".format(sep, sep))
        self.protein_mod = self._protein_mod
        print("{} Loading manually added complexes {}".format(sep, sep))
        self.manual_complexes = self._manual_complexes
        print("{} Getting transcription units from BioCyc {}".format(sep, sep))
        self.TUs = pandas.read_csv(self.config.get('biocyc.TUs', self.directory + "TUs.txt"), index_col=0, sep="\t").fillna('')
        print("{} Getting sigma factors from BioCyc {}".format(sep, sep))
        self.sigmas = self._sigmas
        self.rpod = self._rpod
        print("{} Getting RNA polymerase from BioCyc {}".format(sep, sep))
        self.get_rna_polymerase()
        print("{} Loading generics {}".format(sep, sep))
        self.generic_dict = self._generic_dict
        print("{} Looking for duplicates in provided files {}".format(sep, sep))
        self.check_for_duplicates()
        print("{} Updating generics with genbank {}".format(sep, sep))
        self.get_generics_from_genbank()
        print("{} Loading RNA degradosome {}".format(sep, sep))
        self.rna_degradosome = self._rna_degradosome
        print("{} Loading RNA excision machinery {}".format(sep, sep))
        self.excision_machinery = self._excision_machinery
        print("{} Loading transcription subreactions {}".format(sep, sep))
        self.transcription_subreactions = self._transcription_subreactions
        print("{} Generating transcription units dataframe {}".format(sep, sep))
        self.TU_df = self._TU_df
        self.get_TU_genes()
        print("{} Getting protein location from BioCyc {}".format(sep, sep))
        self.protein_location = self._protein_location
        print("{} Reading ribosomal proteins{}".format(sep, sep))
        self.ribosome_stoich = self._ribosome_stoich
        print("{} Updating ribosomal proteins with BioCyc {}".format(sep, sep))
        self.update_ribosome_stoich()
        print("{} Loading ribosome subreactions {}".format(sep, sep))
        self.ribosome_subreactions = self._ribosome_subreactions
        print("{} Loading ribosome rrna modifications {}".format(sep, sep))
        self.rrna_modifications = self._rrna_modifications
        print("{} Loading amino acid tRNA synthetases {}".format(sep, sep))
        self.amino_acid_trna_synthetase = self._amino_acid_trna_synthetase
        print("{} Loading translation initiation subreactions {}".format(sep, sep))
        self.initiation_subreactions = self._initiation_subreactions
        print("{} Loading translation elongation subreactions {}".format(sep, sep))
        self.elongation_subreactions = self._elongation_subreactions
        print("{} Loading translation termination subreactions {}".format(sep, sep))
        self.termination_subreactions = self._termination_subreactions
        print("{} Loading special trna subreactions {}".format(sep, sep))
        self.special_trna_subreactions = self._special_trna_subreactions
        print("{} Updating tRNA synthetases with BioCyc {}".format(sep, sep))
        self.get_trna_synthetase()
        print("{} Loading trna modifications and targets {}".format(sep, sep))
        self.trna_modification = self._trna_modification
        self.trna_modification_targets = self._trna_modification_targets
        print("{} Loading special modifications {}".format(sep, sep))
        self.special_modifications = self._special_modifications
        print("{} Loading protein translocation pathways {}".format(sep, sep))
        self.translocation_pathways = self._translocation_pathways
        print("{} Loading protein translocation multipliers {}".format(sep, sep))
        self.translocation_multipliers = self.get_translocation_multipliers()
        print("{} Loading lipoprotein precursors {}".format(sep, sep))
        self.lipoprotein_precursors = self.get_lipoprotein_precursors()
        print("{} Loading methionine cleaved proteins {}".format(sep, sep))
        self.cleaved_methionine = self.get_cleaved_methionine()
        print("{} Loading folding information of proteins {}".format(sep, sep))
        self.folding_dict = self._folding_dict
        print("{} Loading subsystem classification for Keffs {}".format(sep, sep))
        self.subsystem_classification = self.get_subsystem_classification()
        print("{} Getting lipids {}".format(sep, sep))
        self.lipids = self.get_lipids()
        print("{} Getting phospholipids {}".format(sep, sep))
        self.phospholipids = self.get_phospholipids()
        print("{} Loading peptide release factors {}".format(sep, sep))
        self.peptide_release_factors = self._peptide_release_factors
        print("{} Updating peptide release factors with BioCyc {}".format(sep, sep))
        self.get_peptide_release_factors()

    def get_genbank_contigs(self):
        if self.is_reference:
            gb_it = Bio.SeqIO.parse(self.directory + "genome.gb", "gb")
        else:
            gb_it = Bio.SeqIO.parse(self.config['genbank-path'], "gb")
        self.contigs = [ i for i in gb_it ]


    def check_minimal_files(self):
        if not os.path.isdir(self.directory):
            os.makedirs(self.directory)
            print("{} directory was created.".format(self.directory))
        if not os.path.isdir(self.blast_directory):
            os.makedirs(self.blast_directory)
            print("{} directory was created.".format(self.blast_directory))

        if not os.path.isfile(self.config.get('biocyc.genes', self.directory + "genes.txt")):
            self.curation_notes['org.check_minimal_files'].append({
                'msg':"genes.txt file not found",
                'importance':'high',
                'to_do':'genes.txt will be generated from genome.gb if create_minimal_files is set to True in parameters.txt. If not, provide genes.txt'})
        if not os.path.isfile(self.config.get('biocyc.prots', self.directory + "proteins.txt")):
            self.curation_notes['org.check_minimal_files'].append({
                'msg':"proteins.txt file not found",
                'importance':'high',
                'to_do':'proteins.txt will be generated from genome.gb if create_minimal_files is set to True in parameters.txt. If not, provide proteins.txt'})
        if not os.path.isfile(self.config.get('biocyc.RNAs', self.directory + "RNAs.txt")):
            self.curation_notes['org.check_minimal_files'].append({
                'msg':"RNAs.txt file not found",
                'importance':'high',
                'to_do':'RNAs.txt will be generated from genome.gb if create_minimal_files is set to True in parameters.txt. If not, provide RNAs.txt'})
        if not os.path.isfile(self.config.get('biocyc.TUs', self.directory + "TUs.txt")):
            self.curation_notes['org.check_minimal_files'].append({
                'msg':"TUs.txt file not found",
                'importance':'high',
                'to_do':'TUs.txt will be generated from genome.gb if create_minimal_files is set to True in parameters.txt. If not, provide TUs.txt'})

    def check_m_model(self):
        m_model = self.m_model

        # Metabolites
        RNA_mets = []
        formula_mets = []
        for m in m_model.metabolites:
            if m.id.startswith("RNA"):
                RNA_mets.append(m)
            if not m.formula:
                formula_mets.append(m.id)

        # Reactions
        subsystem_RXNS = []
        for r in m_model.reactions:
            if not r.subsystem:
                subsystem_RXNS.append(r.id)

        # Warnings
        if RNA_mets:
            self.curation_notes['org.check_m_model'].append({
                'msg':"Metabolites starting with the prefix RNA were removed.",
                'triggered_by':[i.id for i in RNA_mets],
                'importance':'high',
                'to_do':'Check whether the model needs the removed metabolites, and change their name. RNA as a prefix is used for TranscribedGene objects.'})
            m_model.remove_metabolites(RNA_mets)
        if formula_mets:
            self.curation_notes['org.check_m_model'].append({
                'msg':"Some metabolites are missing their formula",
                'triggered_by':formula_mets,
                'importance':'critical',
                'to_do':'Correct the formulas of the listed metabolites. Some metabolite formulas are critical for the completion of this pipeline. If homology is ON, this pipeline will try to fill in the formulas from the reference.'})
        if subsystem_RXNS:
            self.curation_notes['org.check_m_model'].append({
                'msg':"Some reactions are missing their subsystem",
                'triggered_by':subsystem_RXNS,
                'importance':'high',
                'to_do':'Make sure the subsystems of these reactions are correct'})

    def generate_minimal_files(self):
        contigs = self.contigs
        genes = {}
        proteins = {}
        rnas = {}
        tus = {}
        for record in contigs:
            for feature in record.features:
                if feature.type not in {"CDS", "rRNA", "tRNA", "ncRNA", "misc_RNA"}:
                    continue
                if self.locus_tag not in feature.qualifiers: continue
                gene_id = feature.qualifiers[self.locus_tag][0]
                genes[gene_id] = {
                    "Accession-1": gene_id,
                    "Left-End-Position": min([i.start for i in feature.location.parts]),
                    "Right-End-Position": max([i.end for i in feature.location.parts]),
                    "Product": gene_id + "-MONOMER"
                    if feature.type == "CDS"
                    else gene_id + "-{}".format(feature.type),
                }
                tus["TU_{}".format(gene_id)] = {
                    "Genes of transcription unit": gene_id,
                    "Direction": "+" if feature.location.strand == 1 else "-",
                }
                if "RNA" in feature.type and feature.qualifiers.get('product', False):
                    rnas[gene_id] = {"Common-Name": feature.qualifiers["product"][0], "Gene": gene_id}
                if feature.type == "CDS":
                    proteins[gene_id + "-MONOMER"] = {
        #					 "Accession-1": gene_id,
                        "Common-Name": feature.qualifiers["product"][0] if 'product' in feature.qualifiers else gene_id + "-MONOMER",
                        "Genes of polypeptide, complex, or RNA": gene_id,
                        "Locations": "",
        #					 "Gene": gene_id,
                    }
        genes = pandas.DataFrame.from_dict(genes).T
        genes.index.name = "Gene Name"
        genes.to_csv(self.directory + "genes.txt", sep="\t")
        rnas = pandas.DataFrame.from_dict(rnas).T
        rnas.index.name = "(All-tRNAs RNAs Misc-RNAs rRNAs)"
        rnas.to_csv(self.directory + "RNAs.txt", sep="\t")
        proteins = pandas.DataFrame.from_dict(proteins).T
        proteins.index.name = "Proteins"
        proteins.to_csv(self.directory + "proteins.txt", sep="\t")
        tus = pandas.DataFrame.from_dict(tus).T
        tus.to_csv(self.directory + "TUs.txt", sep="\t")

    def sync_files(self):
        if self.is_reference:
            return

        gene_dictionary = self.gene_dictionary
        RNA_df = self.RNA_df
        complexes_df = self.complexes_df
        product_types = {}
        warn_genes = []
        for gene_name,row in gene_dictionary.iterrows():
            gene_id = row['Accession-1']
            if not gene_name or isinstance(gene_name,float):
                warn_genes.append(gene_id)
                continue
            product = row['Product'].split(' // ')[0]
            ### Try to get product type from gene id of type LOCUST_TAG-RNA
            product_type = ''
            if '-' in product and ' ' not in product:
                product_type = re.findall('[a-zA-Z]+',product.split('-')[-1])
                if product_type:product_type = product_type[0]
            ### Set product type to RNA if it is in ID
            if not product_type:
                if 'RNA' in gene_id \
                        or RNA_df['Gene'].str.match(gene_name).any() \
                        or product in RNA_df.index:
                    product_type = 'RNA'
                elif 'MONOMER' in gene_id \
                        or complexes_df['genes'].str.contains('{}\(\d*\)'.format(gene_id),regex=True).any() \
                        or product in complexes_df.index:
                    product_type = 'MONOMER'
                else:
                    warn_genes.append(gene_id)
                    continue

            if ' ' in product or ('RNA' not in product and 'MONOMER' not in product):
                ## Correct product. Likely product is a description and not an actual
                ## product ID like GENE-MONOMER or GENE-tRNA
                product = '{}-{}'.format(gene_name,product_type)
                gene_dictionary.loc[gene_name,'Product'] = product

            product_types[gene_id] = product_type
            ## Sync files
            if 'RNA' in product_type and product not in RNA_df.index:
                print('Adding {} ({}) to RNAs'.format(gene_id,product))
                tmp = pandas.DataFrame.from_dict({ "{}".format(product) : { "Common-Name": product, "Gene": gene_id }}).T
                RNA_df = pandas.concat([RNA_df, tmp], axis = 0, join = 'outer')

            elif product_type == 'MONOMER' and product not in complexes_df.index:
                print('Adding {} ({}) to complexes'.format(gene_id,product))
                #complexes_df = complexes_df.append(
                        #pandas.DataFrame.from_dict(
                            #{
                                #product: {
                                    #"name": product,
                                    #"genes": '{}()'.format(gene_id),
                                    #"source": "Synced",
                                #}
                            #}
                        #).T
                    #)
                tmp = pandas.DataFrame.from_dict({
                    product: {
                        "name": product,
                        "genes": '{}()'.format(gene_id),
                        "source": "Synced",
                        }}).T
                complexes_df = pandas.concat([complexes_df, tmp], axis = 0, join = 'outer')

        self.gene_dictionary = gene_dictionary[pandas.notnull(gene_dictionary.index)]
        self.RNA_df = RNA_df
        self.complexes_df = complexes_df
        self.product_types = product_types

        # Warnings
        if warn_genes:
            self.curation_notes['org.sync_files'].append({
                                'msg':'The types of some genes (e.g. CDS, RNA...) could not be identified',
                                'triggered_by':warn_genes,
                                'importance':'medium',
                                'to_do':'Manually fill the products (with types) of these genes in genes.txt'
            })

    def update_genbank_from_files(self):
        from Bio.SeqFeature import SeqFeature, CompoundLocation, ExactPosition, FeatureLocation, SimpleLocation
        from Bio.SeqRecord import SeqRecord
        if self.is_reference:
            return
        contigs = self.contigs
        gene_sequences = self.gene_sequences
        gene_dictionary = self.gene_dictionary
        RNA_df = self.RNA_df
        complexes_df = self.complexes_df
        product_types = self.product_types
        all_genes_in_gb = self. all_genes_in_gb

        warn_rnas = []
        warn_proteins = []
        warn_position = []
        warn_sequence = []


        # Add new genes
        for gene_name,row in gene_dictionary.iterrows():
            gene_id = row['Accession-1']

            if gene_id not in all_genes_in_gb:
                product = row['Product'].split(' // ')[0]

                ### Try to get product type from gene id of type LOCUST_TAG-RNA
                if gene_id in product_types:
                    product_type = product_types[gene_id]
                else:
                    # Skip those genes whose product type was not identified
                    product_type = 'gene'

                ### Retrieve values to sync with genbank
                if 'RNA' in product_type:
                    if product not in RNA_df.index:
                        warn_rnas.append(gene_id)
                        continue
                    product_name = RNA_df.loc[product]['Common-Name']
                elif product_type == 'MONOMER':
                    product_type = 'CDS'
                    if product not in complexes_df.index:
                        warn_proteins.append(gene_id)
                        continue
                    product_name = complexes_df.loc[product]['name']
                else:
                    product_name = product

                if not row['Left-End-Position'] or not row['Right-End-Position']:
                    warn_position.append(gene_id)
                    continue

                print('Adding {} to genbank file as {}'.format(gene_id,product_type))
                if gene_name not in gene_sequences:
                    warn_sequence.append(gene_name)
                    continue
                gene_seq = gene_sequences[gene_name]
                gene_left = int(row['Left-End-Position'])
                gene_right = int(row['Right-End-Position'])
                new_contig = SeqRecord(seq=gene_seq.seq,
                                      #id = 'contig-{}'.format(gene_id),
                                      id = '{}'.format(gene_id),
                                      name = gene_seq.name,
                                      description = gene_seq.description,
                                      annotations = {
                                          'molecule_type' : 'DNA'
                                      })

                feature0 = SeqFeature(SimpleLocation(ExactPosition(0),ExactPosition(len(gene_seq.seq))),
                                      type='source',
                                      #id = 'contig-{}'.format(gene_id),
                                      id = '{}'.format(gene_id),
                                      qualifiers = {'note':'Added from BioCyc'})
                feature1 = SeqFeature(SimpleLocation(ExactPosition(0),ExactPosition(len(gene_seq.seq)),strand = 1 if gene_left < gene_right else -1),
                                      type=product_type,
                                      id = gene_id,
                                      #strand = 1 if gene_left < gene_right else -1,
                                      qualifiers = {
                                          self.locus_tag:[gene_id],
                                          'product':[product_name]
                                      })

                new_contig.features = [feature0] + [feature1]
                contigs.append(new_contig)

        with open(self.directory + 'genome_modified.gb', 'w') as outfile:
            for contig in contigs:
                Bio.SeqIO.write(contig, outfile, 'genbank')
        # Warnings
        if warn_rnas:
            self.curation_notes['org.update_genbank_from_files'].append({
                                'msg':'Some genes were identified as RNA from its locus_tag, but it is not present in RNAs.txt',
                                'triggered_by':warn_rnas,
                                'importance':'medium',
                                'to_do':'Check whether you should add these genes to RNAs.txt or fix its product value in genes.txt'
            })
        if warn_proteins:
            self.curation_notes['org.update_genbank_from_files'].append({
                                'msg':'Some genes were identified as CDS from its locus_tag, but it is not present in proteins.txt',
                                'triggered_by':warn_proteins,
                                'importance':'medium',
                                'to_do':'Check whether you should add these genes to proteins.txt or fix its product value in genes.txt'
            })
        if warn_position:
            self.curation_notes['org.update_genbank_from_files'].append({
                                'msg':'Could not add some genes in genes.txt to genbank.gb since they lack position information',
                                'triggered_by':warn_position,
                                'importance':'medium',
                                'to_do':'Fill in position information in genes.txt'
            })
        if warn_sequence:
            self.curation_notes['org.update_genbank_from_files'].append({
                                'msg':'Could not add some genes in genes.txt to genbank.gb since they lack sequence information. Are your BioCyc files from the same database version?',
                                'triggered_by':warn_position,
                                'importance':'medium',
                                'to_do':'Add gene sequence in sequences.fasta. Check whether you downloaded the database files from the same BioCyc version.'
            })
    def str_to_dict(self,
                    d):
        regex = ":(?=[-]?\d+(?:$|\.))"
        return (
            {re.split(regex, i)[0]: float(re.split(regex, i)[1]) for i in d.split(",")}
            if d
            else {}
        )

    def dict_to_str(self, d):
        return ",".join(["{}:{}".format(k, v) for k, v in d.items()])

    def generate_complexes_df(self):
        proteins_df = self.proteins_df
        gene_dictionary = self.gene_dictionary
        complexes = {}
        protein_complexes_dict = {}
        warn_proteins = []
        for p, row in proteins_df.iterrows():
            stoich = ""  # No info in BioCyc
            if "dimer" in str(row["Common-Name"]):
                stoich = 2
            genes = row["Genes of polypeptide, complex, or RNA"]
            if isinstance(genes, float):
                warn_proteins.append(p)
                continue
            genes = [
                g for g in genes.split(" // ") if g in gene_dictionary["Accession-1"]
            ]
            complexes[p] = {}
            complexes[p]["name"] = row["Common-Name"]
            complexes[p]["genes"] = " AND ".join(
                [
                    gene_dictionary["Accession-1"][g] + "({})".format(stoich)
                    for g in genes
                ]
            )
            protein_complexes_dict[p] = [
                gene_dictionary["Accession-1"][g] for g in genes
            ]
            complexes[p]["source"] = "BioCyc"
        complexes_df = pandas.DataFrame.from_dict(complexes).T[["name", "genes", "source"]]
        complexes_df.index.name = "complex"

        # Warnings
        if warn_proteins:
            self.curation_notes['org.generate_complexes_df'].append({
                        'msg':'Some proteins have no genes in proteins.txt',
                        'triggered_by':warn_proteins,
                        'importance':'medium',
                        'to_do':'Fill genes in proteins.txt'})
        return complexes_df.fillna({"name": ""})

    def read_gene_dictionary(self):
        filename = self.config.get('biocyc.genes', self.directory + "genes.txt")
        gene_dictionary = pandas.read_csv(filename, sep="\t").set_index('Gene Name',inplace=False)
        gene_dictionary['replicon'] = ''
        warn_genes = []
        if not self.is_reference:
            warn_start = list(gene_dictionary[gene_dictionary['Left-End-Position'].isna()].index)
            warn_end = list(gene_dictionary[gene_dictionary['Right-End-Position'].isna()].index)
            if warn_start:
                self.curation_notes['org.read_gene_dictionary'].append({
                            'msg':'Some genes are missing start positions in genes.txt',
                            'triggered_by':warn_start,
                            'importance':'medium',
                            'to_do':'Complete start positions in genes.txt if those genes are important.'})
            if warn_end:
                self.curation_notes['org.read_gene_dictionary'].append({
                            'msg':'Some genes are missing end positions in genes.txt',
                            'triggered_by':warn_end,
                            'importance':'medium',
                            'to_do':'Complete end positions in genes.txt if those genes are important.'})

            for g, row in gene_dictionary.iterrows():
                if isinstance(row["Accession-1"],float):
                    gene_dictionary.loc[g, "Accession-1"] = g
                    warn_genes.append(g)

        if warn_genes:
            self.curation_notes['org.read_gene_dictionary'].append({
                        'msg':'Some genes are missing Accession-1 IDs in genes.txt',
                        'triggered_by':warn_genes,
                        'importance':'medium',
                        'to_do':'Complete Accession-1 IDs in genes.txt if those genes are important.'})
        return gene_dictionary.fillna("").reset_index().set_index("Gene Name")

    def read_translocation_pathways(self,
                                    df):
        d = {}
        for p in df.index.unique():
            d[p] = {}
            pdf = df.loc[[p]]
            d[p]["keff"] = pdf["keff"][0]
            d[p]["length_dependent_energy"] = pdf["length_dependent_energy"][0]
            d[p]["stoichiometry"] = self.str_to_dict(pdf["stoichiometry"][0])
            d[p]["enzymes"] = {}
            for _, row in pdf.iterrows():
                d[p]["enzymes"][row["enzyme"]] = {
                    "length_dependent": row["length_dependent"],
                    "fixed_keff": row["fixed_keff"],
                }
        return d

    def read_degradosome_stoich(self,
                                df):
        return df["stoich"].to_dict()

    def create_ribosome_stoich(self,
                               df):
        from copy import deepcopy
        ribosome_stoich = deepcopy(dictionaries.ribosome_stoich)
        for s, row in df.iterrows():
            proteins = row["proteins"]
            if proteins:
                proteins = proteins.split(",")
                for p in proteins:
                    if s == "30S":
                        ribosome_stoich["30_S_assembly"]["stoich"][p] = 1
                    elif s == "50S":
                        ribosome_stoich["50_S_assembly"]["stoich"][p] = 1
        return ribosome_stoich

    def write_ribosome_stoich(self, filename):
        d = {"proteins": {"30S": "", "50S": ""}}
        df = pandas.DataFrame.from_dict(d)
        df.index.name = "subunits"
        df.to_csv(filename, sep="\t")

        ribosome_stoich = {
            "30_S_assembly": {"stoich": {"generic_16s_rRNAs": 1}},
            "50_S_assembly": {
                "stoich": {"generic_23s_rRNAs": 1, "generic_5s_rRNAs": 1}
            },
            "assemble_ribosome_subunits": {"stoich": {"gtp_c": 1}},
        }
        return ribosome_stoich

    def check_gene_overlap(self):
        if self.is_reference:
            return

        def get_severity(o):
            if o < 50 :
                return 'critical'
            elif o < 60 :
                return 'high'
            elif o < 70 :
                return 'medium'
            elif o < 80 :
                return 'low'
            else:
                return 0

        m_model_genes = set([g.id for g in self.m_model.genes])
        file_genes = set(self.gene_dictionary['Accession-1'].values)
        all_genes_in_gb = []
        for record in self.contigs:
            for feature in record.features:
                if self.locus_tag not in feature.qualifiers:
                    continue
                all_genes_in_gb.append(feature.qualifiers[self.locus_tag][0])
        self.all_genes_in_gb = all_genes_in_gb
        genbank_genes = set(all_genes_in_gb)

        # Overlaps
        file_overlap = int((len(file_genes & m_model_genes) / len(m_model_genes))*100)
        gb_overlap = int((len(genbank_genes & m_model_genes) / len(m_model_genes))*100)

        print('There is a gene overlap of {}% between M-model and Genbank'.format(gb_overlap))
        print('There is a gene overlap of {}% between M-model and optional files'.format(file_overlap))

        if gb_overlap < 1:
            raise ValueError('Overlap of M-model genes with genbank is too low ({}%)'.format(gb_overlap))
        if file_overlap < 1:
            raise ValueError('Overlap of M-model genes with optional files is too low ({}%)'.format(file_overlap))


        fs = get_severity(file_overlap)
        gs = get_severity(gb_overlap)

        if fs:
            self.curation_notes['org.check_gene_overlap'].append({
                'msg':'M-model has a {} gene overlap with optional files (BioCyc)',
                'importance':fs,
                'to_do':'Check whether optional files where downloaded correctly.'})
        if gs:
            self.curation_notes['org.check_gene_overlap'].append({
                'msg':'M-model has a {} gene overlap with optional files (BioCyc)',
                'importance':gs,
                'to_do':'Check whether genbank was downloaded correctly.'})


    def update_ribosome_stoich(self):
        if self.is_reference:
            return
        complexes_df = self.complexes_df
        ribo_df = complexes_df.loc[
            complexes_df["name"].str.contains("ribosomal.*(?:subunit)?.* protein", regex=True)
        ]
        ribosome_stoich = self.ribosome_stoich
        warn_proteins = []
        for p, row in ribo_df.iterrows():
            if "30S" in row["name"]:
                ribosome_stoich["30_S_assembly"]["stoich"][p] = 1
            elif "50S" in row["name"]:
                ribosome_stoich["50_S_assembly"]["stoich"][p] = 1
            else:
                warn_proteins.append(p)
        self.ribosomal_proteins = ribo_df
        if warn_proteins:
            self.curation_notes['org.update_ribosome_stoich'].append({
                'msg':'Some ribosomal proteins do not contain subunit information (30S, 50S) so they could not be mapped.',
                'triggered_by':warn_proteins,
                'importance':'high',
                'to_do':'Classify them in ribosomal_proteins.csv'})

    def update_complexes_genes_with_genbank(self):
        if self.is_reference:
            return
        element_types = {'CDS', 'rRNA','tRNA', 'ncRNA','misc_RNA'}
        complexes_df = self.complexes_df
        gene_dictionary = self.gene_dictionary
        RNA_df = self.RNA_df

        warn_locus = []
        for record in self.contigs:
            for feature in record.features:
                if feature.type not in element_types:
                    continue
                if self.locus_tag not in feature.qualifiers:
                    warn_locus.append(feature.qualifiers)
                    continue
                gene_id = feature.qualifiers[self.locus_tag]
                if not gene_id:
                    continue
                gene_id = gene_id[0]
                left_end = min([i.start for i in feature.location.parts])
                right_end = max([i.end for i in feature.location.parts])
                if not gene_dictionary["Accession-1"].str.contains(gene_id.replace('(', '\(').replace(')', '\)')).any():
                    print("Adding {} to genes from genbank".format(gene_id))
                    feature_type = feature.type
                    if feature_type == 'CDS':
                        feature_type = 'MONOMER'
                    tmp = pandas.DataFrame.from_dict({
                                gene_id: {
                                    "Accession-1": gene_id,
                                    "Left-End-Position": left_end,
                                    "Right-End-Position": right_end,
                            "Product": "{}-{}".format(gene_id,feature_type)
                            }}).T
                    gene_dictionary = pandas.concat([gene_dictionary, tmp], axis = 0, join = 'outer')
                else:
                    accession = gene_dictionary[
                        gene_dictionary["Accession-1"].str.contains(gene_id.replace('(', '\(').replace(')', '\)'))
                    ].index.values[0]

                gene_name = gene_dictionary[gene_dictionary["Accession-1"].str.contains(gene_id.replace('(', '\(').replace(')', '\)'))].index[0]
                if 'product' in feature.qualifiers:
                    name_annotation = feature.qualifiers["product"][0]
                else:
                    name_annotation = gene_name
                if feature.type == 'CDS':
                    product = gene_name + '-MONOMER'
                    if not complexes_df["genes"].str.contains(gene_id).any():
                        print("Adding {} ({}) to complexes from genbank".format(gene_id,product))
                        tmp = pandas.DataFrame.from_dict({
                                    product: {
                                        "name": name_annotation,
                                        "genes": "{}()".format(gene_id),
                                        "source": "GenBank",
                                }}).T
                        complexes_df = pandas.concat([complexes_df, tmp], axis = 0, join = 'outer')

                else: # It's not CDS, but an RNA
                    product = "{}-{}".format(gene_name,feature.type)
                    if not RNA_df["Gene"].str.contains(gene_name.replace('(', '\(').replace(')', '\)')).any():
                        print("Adding {} ({}) to RNAs from genbank".format(gene_id,product))
                        tmp = pandas.DataFrame.from_dict(
                                {
                                   product : {
                                        "Common-Name": name_annotation,
                                        "Gene": gene_name
                                    }
                                }
                            ).T
                        RNA_df = pandas.concat([RNA_df, tmp], axis = 0, join = 'outer')
                gene_dictionary.loc[gene_name]['Product'] = product # Ensuring product is the same.
                gene_dictionary.loc[gene_name]["Left-End-Position"] = left_end
                gene_dictionary.loc[gene_name]["Right-End-Position"] = right_end
                gene_dictionary.loc[gene_name]["replicon"] = record.id
        self.complexes_df = complexes_df
        gene_dictionary.index.name = "Gene Name"
        self.gene_dictionary = gene_dictionary
        self.RNA_df = RNA_df

        if warn_locus:
            self.curation_notes['org.update_complexes_genes_with_genbank'].append({
                'msg':'Some genbank features do not have locus_tag.',
                'triggered_by':warn_locus,
                'importance':'high',
                'to_do':'Check whether these features are necessary, and correct their locus_tag. If they have been completed from other provided files, ignore.'})

    def purge_genes_in_model(self):
        from cobra.manipulation.delete import remove_genes
        m_model = self.m_model
        gene_dictionary = self.gene_dictionary
        gene_list = []
        for g in m_model.genes:
            if g.id not in gene_dictionary['Accession-1'].values:
                gene_list.append(g)
        remove_genes(m_model, gene_list, remove_reactions=False)
        # Warnings
        if gene_list:
            self.curation_notes['org.purge_genes_in_model'].append({
                'msg':'Some genes in m_model were not found in genes.txt or genome.gb. These genes were skipped.',
                'triggered_by':[g.id for g in gene_list],
                'importance':'high',
                'to_do':'Confirm the gene is correct in the m_model. If so, add it to genes.txt'})
    def get_trna_synthetase(self):
        if self.is_reference:
            return

        def find_aminoacid(trna_string):
            trna_string = trna_string.lower()
            for aa, rx in dictionaries.amino_acid_regex.items():
                if re.search(rx, trna_string):
                    return aa
            return 0

        org_amino_acid_trna_synthetase = self.amino_acid_trna_synthetase
        generic_dict = self.generic_dict
        d = {}
        for k,v in org_amino_acid_trna_synthetase.copy().items():
            if isinstance(v,list):
                d[k] = set(v)
            elif isinstance(v,str):
                if v:
                    d[k] = set([v])
                else:
                    d[k] = set()
        proteins_df = self.proteins_df["Common-Name"].dropna()
        trna_ligases = proteins_df[
            proteins_df.str.contains(
                "tRNA [-]{,2}(?:synthetase|ligase)(?!.*subunit.*)", regex=True
            )
        ].to_dict()
        warn_ligases = []
        for cplx, trna_string in trna_ligases.items():
            aa = find_aminoacid(trna_string)
            if aa:
                d[aa].add(cplx)

        for aa,c_set in d.items():
            c_list = list(c_set)
            if len(c_list) == 1:
                d[aa] = c_list[0]
            elif len(c_list) > 1:
                generic = 'generic_{}_ligase'.format(aa.split('__L_c')[0])
                generic_dict[generic] = {'enzymes':c_list}
                d[aa] = generic
            else:
                d[aa] = 'CPLX_dummy'
                warn_ligases.append(aa)
        self.amino_acid_trna_synthetase = d

        # Warnings
        if warn_ligases:
            self.curation_notes['org.get_trna_synthetase'].append({
                'msg':'No tRNA ligases were found for some amino acids. Assigned CPLX_dummy.',
                'triggered_by':warn_ligases,
                'importance':'high',
                'to_do':'Check whether your organism should have a ligase for these amino acids, or if you need to add a reaction to get it (e.g. tRNA amidotransferases)'})

    def get_peptide_release_factors(self):
        if self.is_reference:
            return

        proteins_df = self.proteins_df["Common-Name"].dropna()
        peptide_release_factors = self.peptide_release_factors
        generics = self.generic_dict
        rf = proteins_df[proteins_df.str.contains("peptide.*release.*factor")]
        if rf.size:
            if not peptide_release_factors["UAG"]['enzyme'] and rf.str.contains("1").any():
                peptide_release_factors["UAG"]['enzyme'] = rf[rf.str.contains("1")].index[0]
                generics["generic_RF"]['enzymes'].append(peptide_release_factors["UAG"]['enzyme'])
            if not peptide_release_factors["UGA"]['enzyme'] and rf.str.contains("2").any():
                peptide_release_factors["UGA"]['enzyme'] = rf[rf.str.contains("2")].index[0]
                generics["generic_RF"]['enzymes'].append(peptide_release_factors["UGA"]['enzyme'])

    def gb_to_faa(self, org_id, outdir = False, element_types = {"CDS"}):
        ## Create FASTA file with AA sequences for BLAST
        contigs = self.contigs

        if not outdir:
            outdir = self.blast_directory

        #outdir += "blast_files_and_results/"
        FASTA_file = outdir + "{}.faa".format(org_id)
#         FASTA_file = "{}.faa".format(org_id)

        file = open(FASTA_file, "w")
        for contig in contigs:
            for feature in contig.features:
                if feature.type not in element_types \
                    or "translation" not in feature.qualifiers \
                    or self.locus_tag not in feature.qualifiers:
                    continue
                file.write(
                    ">{}\n".format(feature.qualifiers[self.locus_tag][0])
                )  # Some way to identify which qualifier meets regular expression?
                file.write("{}\n".format(feature.qualifiers["translation"][0]))

    def get_sigma_factors(self):
        complexes_df = self.complexes_df

        sigma_df = complexes_df.loc[
            complexes_df["name"].str.contains(
                "RNA polymerase.*sigma.*[factor.*]?.*|sigma.*[factor.*]?.*RNA polymerase", regex=True
            )
        ]
        if not sigma_df.shape[0]:
            self.curation_notes['org.get_sigma_factors'].append({
                'msg':"No sigma factors could be identified from proteins.txt",
                'importance':'critical',
                'to_do':'Manually define sigmas in sigma_factors.csv'})
            random_cplx = random.choice(complexes_df.index)
            sigma_df = complexes_df.loc[[random_cplx]]

        ## Get sigmas automatically
        def process_sigma_name(name, row):
            name = name.split("RNA polymerase")[-1]
            replace_list = ["sigma", "factor", "sup"]
            for r in replace_list:
                name = name.replace(r, "")
            name = "".join(re.findall("[a-zA-Z0-9]{1,}", name))
            if not name:
                name = "_".join(row["genes"])
            return "RNAP_" + name
        # Find RpoD to add as default sigma
        sigmas = {}
        for s, row in sigma_df.iterrows():
            sigmas[s] = {}
            sigmas[s]["complex"] = process_sigma_name(s, row)
            sigmas[s]["genes"] = row["genes"]
            sigmas[s]["name"] = row["name"]
        sigma_df = pandas.DataFrame.from_dict(sigmas).T
        sigma_df.index.name = "sigma"
        return sigma_df

    def get_rpod(self):
        sigma_df = self.sigmas
        rpod = sigma_df[sigma_df["name"].str.contains("RpoD")].index.to_list()
        if not rpod:
            rpod_re = "|".join(["70", "sigma-A", "sigA", "SigA","Sigma-A"])
            rpod = sigma_df[sigma_df["name"].str.contains(rpod_re)].index.to_list()
        if rpod:
            rpod = rpod[0]
            # Warnings
            self.curation_notes['org.get_sigma_factors'].append({
                'msg':"{} was identified as RpoD. If this is not true, define RpoD!".format(rpod),
                'importance':'high',
                'to_do':'Check whether you need to correct RpoD by running me_builder.org.rpod = correct_rpod'})
        else:
            rpod = random.choice(sigma_df.index)
            # Warnings
            self.curation_notes['org.get_sigma_factors'].append({
                'msg':"RpoD randomly assigned to {}".format(rpod),
                'importance':'critical',
                'to_do':'genome.gb does not have a valid annotation for RpoD. A random identified sigma factor in me_builder.org.sigmas was set as RpoD so that the builder can continue running. Set the correct RpoD by running me_builder.org.rpod = correct_rpod'})
        return rpod

    def get_rna_polymerase(self, force_RNAP_as=""):
        RNAP = ""
        if force_RNAP_as:
            RNAP = force_RNAP_as
        else:
            complexes_df = self.complexes_df
            rnap_regex = "(?:RNA polymerase.*core enzyme|DNA.*directed.*RNA polymerase.*)(?!.*subunit.*)"
            RNAP = complexes_df[
                complexes_df["name"].str.contains(rnap_regex, regex=True)
            ].index.to_list()
            if RNAP:
                RNAP = RNAP[0]
                # Warnings
                self.curation_notes['org.get_rna_polymerase'].append({
                    'msg':"{} was identified as RNA polymerase".format(RNAP),
                    'importance':'high',
                    'to_do':'Check whether you need to correct RNAP by running me_builder.org.get_rna_polymerase(force_RNAP_as=correct_RNAP)'})
            else:
                #rnap_regex = "(RNA polymerase.*core enzyme|DNA.*directed.*RNA polymerase)(?=.*subunit.*)"
                rnap_regex = "(?:RNA polymerase.*core enzyme|DNA.*directed.*RNA polymerase)(?=.*subunit.*)"
                RNAP_genes = complexes_df[
                    complexes_df["name"].str.contains(rnap_regex, regex=True)
                ].index.to_list()
                RNAP_genes = [
                    g.split("-MONOMER")[0] for g in RNAP_genes if "-MONOMER" in g
                ]
                if RNAP_genes:
                    RNAP = "RNAP-CPLX"
                    complexes_df = complexes_df.append(
                        pandas.DataFrame.from_dict(
                            {
                                RNAP: {
                                    "name": "DNA-directed RNA polymerase",
                                    "genes": " AND ".join(
                                        ["{}()".format(g) for g in RNAP_genes]
                                    ),
                                    "source": "GenBank",
                                }
                            }
                        ).T
                    )
                    self.curation_notes['org.get_rna_polymerase'].append({
                        'msg':"RNAP was identified with subunits {}".format(
                            ", ".join(RNAP_genes)
                        ),
                        'importance':'medium',
                        'to_do':'Check whether the correct proteins were called as subunits of RNAP. If not find correct RNAP complex and run me_builder.org.get_rna_polymerase(force_RNAP_as=correct_RNAP)'})
                else:
                    RNAP = random.choice(complexes_df.index)
                    self.curation_notes['org.get_rna_polymerase'].append({
                        'msg':"Could not identify RNA polymerase".format(RNAP),
                        'importance':'critical',
                        'to_do':'Find correct RNAP complex and run me_builder.org.get_rna_polymerase(force_RNAP_as=correct_RNAP)'})
        self.RNAP = RNAP
        self.complexes_df = complexes_df
        self.sigma_factor_complex_to_rna_polymerase_dict = self.sigmas[
            "complex"
        ].to_dict()
        self.rna_polymerase_id_by_sigma_factor = {}
        for k, v in self.sigma_factor_complex_to_rna_polymerase_dict.items():
            self.rna_polymerase_id_by_sigma_factor[v] = {
                "sigma_factor": k,
                "polymerase": self.RNAP,
            }
        self.rna_polymerases = list(self.rna_polymerase_id_by_sigma_factor.keys())

    def get_TU_genes(self):
        TUs = self.TUs
        gene_dictionary = self.gene_dictionary
        genes_to_TU = {}
        TU_to_genes = {}
        for tu, row in TUs.iterrows():
            genes = row["Genes of transcription unit"]
            if not genes:
                continue
            for g in genes.split(" // "):
                if g not in gene_dictionary.index:
                    continue
                genes_to_TU[gene_dictionary["Accession-1"][g]] = tu

                if tu not in TU_to_genes:
                    TU_to_genes[tu] = []
                TU_to_genes[tu].append(g)
        self.genes_to_TU = genes_to_TU
        self.TU_to_genes = TU_to_genes

    def get_TU_df(self):
        TUs = self.TUs
        gene_dictionary = self.gene_dictionary
        rpod = self.rpod
        TU_dict = {}
        warn_genes = []
        warn_tus = []
        for tu, row in TUs.iterrows():
            sites = []
            start = []
            end = []
            genes = []
            replicons = []
            for g in row["Genes of transcription unit"].split(" // "):
                if g not in gene_dictionary.index:
                    warn_genes.append(g)
                    continue
                genes.append(gene_dictionary["Accession-1"][g])
                #sites.append(int(gene_dictionary["Left-End-Position"][g]))
                #sites.append(int(gene_dictionary["Right-End-Position"][g]))
                start.append(int(gene_dictionary["Left-End-Position"][g]))
                end.append(int(gene_dictionary["Right-End-Position"][g]))
                replicons.append(gene_dictionary["replicon"][g])
            if not genes:
                warn_tus.append(tu)
                continue
            sigma = rpod  # Default RpoD
            rho_dependent = True  # Default True
            tu_name = "{}_from_{}".format(tu, sigma)
            TU_dict[tu_name] = {}
            TU_dict[tu_name]["genes"] =  ','.join(genes)
            TU_dict[tu_name]["rho_dependent"] = rho_dependent
            TU_dict[tu_name]["rnapol"] = sigma
            TU_dict[tu_name]["tss"] = None
            TU_dict[tu_name]["strand"] = row["Direction"] if row["Direction"] else '+'
            #TU_dict[tu_name]["start"] = int(min(sites))+1
            TU_dict[tu_name]["start"] = ','.join([ str(x+1) for x in start ])
            #TU_dict[tu_name]["stop"] = int(max(sites))
            TU_dict[tu_name]["stop"] = ','.join([ str(x) for x in end ])
            TU_dict[tu_name]["replicon"] = ','.join(replicons)
        df = pandas.DataFrame.from_dict(TU_dict).T[
            #["start", "stop", "tss", "strand", "rho_dependent", "rnapol","replicon"]
            ['replicon', 'genes', 'start', 'stop', 'tss', 'strand', 'rho_dependent', 'rnapol']
        ]
        df.index.name = "TU_id"

        # Warnings
        if warn_genes or warn_tus:
            if warn_genes:
                self.curation_notes['org.get_TU_df'].append({
                        'msg':"Some genes appear in TUs.txt but not in genes.txt",
                        'triggered_by':warn_genes,
                        'importance':'medium',
                        'to_do':'If those genes are supposed to be in the model, fill them in genes.txt'})
            if warn_tus:
                self.curation_notes['org.get_TU_df'].append({
                        'msg':"Some TUs are either empty (no genes in TUs.txt) or contain genes that are not in genes.txt",
                        'triggered_by':warn_tus,
                        'importance':'medium',
                        'to_do':'If those TUs contain genes that are supposed to be in the model, fill them in TUs.txt and genes.txt'})
        return df

    def get_protein_location(self):
        def process_location_dict(location, location_interpreter):
            new_location = {}
            for k, v in location.items():
                if isinstance(v, float):
                    continue
                for loc in v.split(" // "):
                    if loc in location_interpreter.index:
                        new_location[k] = location_interpreter["interpretation"][loc]
                        break
            return new_location

        complexes_df = self.complexes_df
        proteins_df = self.proteins_df
        gene_dictionary = self.gene_dictionary
        location_interpreter = self.location_interpreter

        protein_location = pandas.DataFrame.from_dict(
            {
                "Complex_compartment": {},
                "Protein": {},
                "Protein_compartment": {},
                "translocase_pathway": {},
            }
        )
        gene_location = process_location_dict(
            proteins_df.set_index("Genes of polypeptide, complex, or RNA")["Locations"]
            .dropna()
            .to_dict(),
            location_interpreter,
        )
        cplx_location = process_location_dict(
            proteins_df["Locations"].dropna().to_dict(), location_interpreter
        )
        gene_dictionary = gene_dictionary.reset_index().set_index("Accession-1")
        for c, row in complexes_df.iterrows():
            if c in cplx_location:
                c_loc = cplx_location[c]
            else:
                continue
            for gene_string in complexes_df["genes"][c].split(' AND '):
                gene = re.findall('.*(?=\(\d*\))', gene_string)[0]
                gene = gene_dictionary.loc[[gene]]["Gene Name"]
                for gene_ in gene: # In case of duplicates
                    if gene_ in gene_location:
                        #protein_location = protein_location.append(
                        #pandas.DataFrame.from_dict(
                                #{
                                    #c: {
                                        #"Complex_compartment": c_loc,
                                        #"Protein": gene_string,
                                        #"Protein_compartment": gene_location[gene_],
                                        #"translocase_pathway": "s",
                                    #}
                                #}
                            #).T
                        #)
                        tmp = pandas.DataFrame.from_dict({
                            c: {
                                "Complex_compartment": c_loc,
                                "Protein": gene_string,
                                "Protein_compartment": gene_location[gene_],
                                "translocase_pathway": "s",
                                }}).T
                        protein_location = pandas.concat([protein_location, tmp], axis = 0, join = 'outer')
        protein_location.index.name = "Complex"
        return protein_location

    def get_translocation_multipliers(self):
        filename = self.directory + "translocation_multipliers.csv"
        try:
            return pandas.read_csv(filename, index_col=0).to_dict()
        except:
            self.curation_notes['org.get_translocation_multipliers'].append({
                'msg':'No translocation_multipliers.csv file found',
                'importance':'low',
                'to_do':'Fill in me_builder.org.translocation_multipliers'})
            return dict()

    def get_lipoprotein_precursors(self):
        filename = self.directory + "lipoprotein_precursors.csv"
        try:
            return pandas.read_csv(filename, index_col=0).to_dict()["gene"]
        except:
            self.curation_notes['org.get_lipoprotein_precursors'].append({
                'msg':'No lipoprotein_precursors.csv file found',
                'importance':'low',
                'to_do':'Fill in me_builder.org.lipoprotein_precursors'})
            return dict()

    def get_cleaved_methionine(self):
        filename = self.directory + "cleaved_methionine.csv"
        try:
            return list(pandas.read_csv(filename,index_col=0).index)
        except:
            pandas.DataFrame.from_dict({'cleaved_methionine_genes':{}}).set_index('cleaved_methionine_genes').to_csv(filename)
            self.curation_notes['org.get_cleaved_methionine'].append({
                'msg':'No cleaved_methionine.csv file found',
                'importance':'low',
                'to_do':'Fill in me_builder.org.cleaved_methionine or cleaved_methionine.csv'})
            return list()

    def get_subsystem_classification(self):
        if self.is_reference:
            return None

        filename = self.directory + "subsystem_classification.csv"
        d = {}
        try:
            df = pandas.read_csv(filename, index_col=0)
            for c in df.columns:
                for s in df[df.c == 1].index:
                    d[s] = c
        except:
            self.curation_notes['org.get_subsystem_classification'].append({
                'msg':'No subsystem_classification.csv file found',
                'importance':'low',
                'to_do':'Check and correct the generated subsystem_classification.csv'})
            subsystems = set(r.subsystem for r in self.m_model.reactions if r.subsystem)
            df = {}
            for s in subsystems:
                d[s] = "central_CE"
                df[s] = {}
                df[s]["central_CE"] = 0
                df[s]["central_AFN"] = 0
                df[s]["intermediate"] = 0
                df[s]["secondary"] = 0
                df[s]["other"] = 1
            df = pandas.DataFrame.from_dict(df).T
            df.to_csv(filename)
        return d

    def get_reaction_keffs(self):
        if self.is_reference:
            return None

        m_model = self.m_model
        subsystem_classification = self.subsystem_classification
        enz_rxn_assoc_df = self.enz_rxn_assoc_df
        rxn_keff_dict = {}
        reaction_dirs = ["FWD", "REV"]
        keffs = {
            "central_CE": 79,
            "central_AFN": 18,
            "intermediate": 5.2,
            "secondary": 2.5,
            "other": 65,
        }
        for reaction, row in enz_rxn_assoc_df.iterrows():
            r = m_model.reactions.get_by_id(reaction)
            subsystem = r.subsystem
            if subsystem in subsystem_classification:
                classification = subsystem_classification[subsystem]
            else:
                classification = "other"
            keff = keffs[classification]
            cplxs = row["Complexes"].split(" OR ")
            for c in cplxs:
                for d in reaction_dirs:
                    r = "{}_{}_{}".format(reaction, d, c)
                    rxn_keff_dict[r] = {}
                    rxn_keff_dict[r]["complex"] = c
                    rxn_keff_dict[r]["keff"] = keff
        self.reaction_median_keffs = pandas.DataFrame.from_dict(rxn_keff_dict).T
        self.reaction_median_keffs.index.name = "reaction"

    def get_phospholipids(self):
        m_model = self.m_model
        return [
            str(m.id) for m in m_model.metabolites.query(re.compile("^pg[0-9]{2,3}_.$"))
        ]
    def get_lipids(self):
        m_model = self.m_model
        return [
            str(m.id) for m in m_model.metabolites.query(re.compile("^[a-z]*[0-9]{2,3}_.$"))
        ]

    def generate_metabolites_file(self):
        m_model = self.m_model
        d = {}
        seen = set()
        for m in m_model.metabolites:
            if m in seen:
                continue
            m_root = m.id[:-2]
            same_mets = m_model.metabolites.query(
                re.compile("^" + m_root + "_[a-z]{1}$")
            )
            compartment_string = " AND ".join(
                m_model.compartments[i.compartment] for i in same_mets
            )
            d[m_root] = {
                "name": m.name,
                "formula": m.formula,
                "compartment": compartment_string,
                "data_source": m_model.id,
            }
            seen = seen | set(same_mets)
        self.metabolites = pandas.DataFrame.from_dict(d).T
        self.metabolites.index.name = "id"

    def generate_reactions_file(self):
        def is_spontaneous(r):
            return (
                1
                if "spontaneous" in r.name or "diffusion" in r.name and not r.genes
                else 0
            )

        m_model = self.m_model
        d = {}
        for r in m_model.reactions:
            d[r.id] = {
                "description": r.name,
                "is_reversible": int(r.reversibility),
                "data_source": m_model.id,
                "is_spontaneous": is_spontaneous(r),
            }
        self.reactions = pandas.DataFrame.from_dict(d).T
        self.reactions.index.name = "name"

    def generate_reaction_matrix(self):
        m_model = self.m_model
        m_to_me = self.m_to_me_mets
        df = pandas.DataFrame.from_dict(
            {"Reaction": {}, "Metabolites": {}, "Compartment": {}, "Stoichiometry": {}}
        ).set_index("Reaction")
        warn_rxns = []
        for rxn in m_model.reactions:
            if set(
                [
                    m_to_me.loc[met.id, "me_name"]
                    for met in rxn.metabolites
                    if met.id in m_to_me.index
                ]
            ) == set(["eliminate"]):
                warn_rxns.append(rxn.id)
                continue
            for metabolite in rxn.metabolites:
                compartment = m_model.compartments[metabolite.compartment]
                met = metabolite.id[:-2]
                if metabolite.id in m_to_me.index:
                    if m_to_me.loc[metabolite.id, "me_name"] == "eliminate":
                        continue
                    met = m_to_me.loc[metabolite.id, "me_name"]
                coefficient = rxn.get_coefficient(metabolite)
                tmp = pandas.DataFrame.from_dict({
                    rxn.id: {
                        "Metabolites": met,
                        "Compartment": compartment,
                        "Stoichiometry": coefficient,
                        }}).T
                df = pandas.concat([df, tmp], axis = 0, join = 'outer')
        df.index.name = "Reaction"
        self.reaction_matrix = df

        df.to_csv(self.directory + 'reaction_matrix.txt')
        # Warnings
        if warn_rxns:
            self.curation_notes['org.generate_reaction_matrix'].append({
                'msg':'Some reactions consisted only of metabolites marked for elimination in m_to_me_mets.csv, so they were removed',
                'triggered_by':warn_rxns,
                'importance':'high',
                'to_do':'Some of these reactions can be essential for growth. If you want to keep any of these reactions, or modify them, add them to reaction_corrections.csv'})

    def get_generics_from_genbank(self):
        if self.is_reference:
            return None
        contigs = self.contigs
        generic_dict = self.generic_dict
        warn_generics = []
        for contig in contigs:
            for feature in contig.features:
                if "rRNA" in feature.type:
                    gene = "RNA_" + feature.qualifiers[self.locus_tag][0]
                    if any("5S" in i for i in feature.qualifiers["product"]):
                        cat = "generic_5s_rRNAs"
                    elif any("16S" in i for i in feature.qualifiers["product"]):
                        cat = "generic_16s_rRNAs"
                    elif any("23S" in i for i in feature.qualifiers["product"]):
                        cat = "generic_23s_rRNAs"
                    else:
                        cat = 0
                    if cat:
                        print("{} to {}".format(gene, cat))
                        generic_dict[cat]['enzymes'].append(gene)
        for k, v in generic_dict.items():
            if not v:
                warn_generics.append(k)
        if warn_generics:
            self.curation_notes['org.get_generics_from_genbank'].append({
                'msg':'Some generics in me_builder.org.generic_dict are empty.',
                'triggered_by':warn_generics,
                'importance':'high',
                'to_do':'Curate and fill generics in generics.csv or directly in me_builder.org.generic_dict'})

    def check_for_duplicates(self):
        from coralme.builder.helper_functions import change_reaction_id
        import collections
        # Duplicates within datasets
        info = {
            'complexes_df' : list(self.complexes_df.index),
            'RNA_df' : list(self.RNA_df.index),
            'gene_dictionary' : list(self.gene_dictionary.index),
            'reactions' : list([i.id for i in self.m_model.reactions]),
            'Accession-1' : list(self.gene_dictionary['Accession-1'].values)
        }
        warn_dups = {}
        for k,v in info.items():
            if len(v) != len(set(v)):
                warn_dups[k] = [item for item, count in collections.Counter(v).items() if count > 1]

        if warn_dups:
            self.curation_notes['org.check_for_duplicates'].append({
                'msg':'Some datasets contain duplicate indices or Accession IDs.',
                'triggered_by' : [warn_dups],
                'importance':'critical',
                'to_do':'Remove or fix duplicates. If duplicates are in Accession-1, they are processed as different possibilities to get the same enzyme, so they are added as generic complexes. Check!'})
            if 'Accession-1' in warn_dups and not self.is_reference:
                for d in warn_dups['Accession-1']:
                    if not d: continue
                    dups = self.gene_dictionary[self.gene_dictionary['Accession-1'].str.contains(d)]
                    self.generic_dict['generic_{}'.format(d)] = {"enzymes":[i for i in dups['Product'].values if i]}

        # Duplicates between different datasets
        cplxs = set(info['complexes_df'])
        rnas = set(info['RNA_df'])
        genes = set(info['gene_dictionary'])
        rxns = set(info['reactions'])
        occ = {}
        for i in cplxs|rnas|genes|rxns:
            occ[i] = {'proteins':0,'RNAs':0,'genes':0,'reactions':0}
            if i in cplxs:
                occ[i]['proteins'] += 1
            if i in rnas:
                occ[i]['RNAs'] += 1
            if i in genes:
                occ[i]['genes'] += 1
            if i in rxns:
                occ[i]['reactions'] += 1
        df = pandas.DataFrame.from_dict(occ).T
        df = df[df['reactions'] == 1]
        dup_df = df[df.sum(1)>1]
        for c,row in dup_df.iterrows():
            if row['reactions']:
                change_reaction_id(self.m_model,c,c+'_rxn')
                print('Changed reaction ID from {} to {} to prevent the conflict between: {}'.format(c,c+'_rxn',' and '.join([j for j,k in row.items() if k])))
            else:
                raise ValueError('The identifier {} is duplicated in {}. Please fix!'.format(c,' and '.join([j for j,k in row.items() if k])))

    def generate_curation_notes(self):
        import json
        curation_notes = self.curation_notes
        filename = self.directory + '/curation_notes.txt'
        file = open(filename,'w')
        for k,v in curation_notes.items():
            file.write('\n')
            for w in v:
                file.write('{} {}@{} {}\n'.format('#'*20,w['importance'],k,'#'*20))
                file.write('{} {}\n'.format('*'*10,w['msg']))
                if 'triggered_by' in w:
                    file.write('The following items triggered the warning:\n')
                    for i in w['triggered_by']:
                        if isinstance(i,dict):
                            file.write('\n')
                            file.write(json.dumps(i))
                            file.write('\n')
                        else:
                            file.write(i + '\n')
                file.write('\n{}Solution:\n{}\n\n'.format('*'*10,w['to_do']))
            file.write('\n\n')
        file.close()
