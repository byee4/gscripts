#!/usr/bin/env python
# coding=utf-8

# Parse command line arguments
import os
import sys

import argparse
import pandas as pd


# Submit jobs to the cluster
from gscripts.qtools import Submitter

WALLTIME = '2:00:00'

'''
Author: olga
Date created: 7/12/13 9:38 AM

The purpose of this program is to write submitter scripts to perform MISO
analysis on a large amount of files. This script assumes paired-end reads.

# **Note** for some reason,

Example runs:



TODO: deprecate the non-queue way of running
'''

# Class: CommandLine
class CommandLine(object):
    def __init__(self, inOpts=None):
        self.parser = argparse.ArgumentParser(
            description='''Write a script to perform MISO analysis
            on individual samples. By default, this is submitted to TSCC,
            unless "--do-not-submit" is specified.
            ''',
            add_help=True, prefix_chars='-')
        samples = self.parser.add_mutually_exclusive_group(required=True)
        samples.add_argument('--bam', type=str,
                             action='store', default='',
                             help='A single BAM file')
        samples.add_argument('--sample-info', type=str, action='store',
                             help='A tab-delimited file with Bam files as '
                                  'column 1 and the sample Ids as column 2 ('
                                  'no header). If "--do-not-submit" is off, '
                                  'this will submit an '
                                  'array job to be a nice cluster user')
        self.parser.add_argument('--sample-id', type=str,
                                 action='store',
                                 help='sample ID. required if using --bam',
                                 required=False)
        self.parser.add_argument('--genome', type=str, action='store',
                                 required=True, help='Which genome to use')
        self.parser.add_argument('--output-sh', type=str, required=False,
                                 action='store',
                                 help="The name of the .sh script created for "
                                      "one-touch action. Required if using "
                                      "'--bam' for a single sample."
                                      "Not used with '--sample-info', "
                                      "where each sample "
                                      "gets its own sh file.")
        self.parser.add_argument('--walltime',
                                 action='store', default='1:00:00',
                                 help='Walltime of each submitted job. '
                                      '(default=1:00:00 aka 1 hour)')
        self.parser.add_argument('--nodes=', action='store', default=1,
                                 help='Number of nodes to request. '
                                      '(default=1)')
        self.parser.add_argument('--ppn', action='store', default=16,
                                 help='Processors per node. (default=16)')
        self.parser.add_argument('-l', '--read-length', required=False,
                                 help='(optional) Read length of samples. If '
                                      'not provided, the length of the first '
                                      'read of the bam file is used.')
        self.parser.add_argument('--do-not-submit',
                                 action='store_true', default=False,
                                 help='Whether or not to actually submit the '
                                      'final file.')

        if inOpts is None:
            self.args = vars(self.parser.parse_args())
        else:
            self.args = vars(self.parser.parse_args(inOpts))

    def do_usage_and_die(self, str):
        '''
        If a critical error is encountered, where it is suspected that the
        program is not being called with consistent parameters or data, this
        method will write out an error string (str), then terminate execution
        of the program.
        '''
        import sys

        print >> sys.stderr, str
        self.parser.print_usage()
        return 2


# Class: Usage
class Usage(Exception):
    '''
    Used to signal a Usage error, evoking a usage statement and eventual
    exit when raised
    '''

    def __init__(self, msg):
        self.msg = msg


class MisoPipeline(object):
    def __init__(self, bam, sample_info_file,
                 sample_id, output_sh,
                 genome, walltime, nodes=1, ppn=16,
                 submit=False, read_length=None):
        """
        Parameters
        ----------


        Returns
        -------


        Raises
        ------
        """
        self.sample_info_file = sample_info_file

        if self.sample_info_file is not None:
            sample_info = pd.read_table(self.sample_info_file, header=None)
            self.bams = sample_info[0]
            self.sample_ids = sample_info[1]
            self.sh_files = ['{}.miso.sh'.format(bam) for bam in self.bams]
            self.multiple_samples = True
        else:
            self.sample_ids = [sample_id]
            self.bams = [bam]
            self.sh_files = [output_sh]
            self.multiple_samples = False

        self.genome = genome
        self.walltime = walltime
        self.submit = submit

        self.nodes = nodes
        self.ppn = ppn
        self.read_length = self.read_length

        all_samples_commands = []

        for bam, sample_id, sh_file in zip(self.bams, self.sample_ids,
                                           self.sh_files):
            self._write_single_sample(bam, sample_id, sh_file)

            sh_command = 'bash {}'.format(sh_file)
            if self.submit and not self.multiple_samples:
                commands = [sh_command]
                sub = Submitter(commands, job_name='miso',
                                sh_filename='{}.qsub.sh'.format(sh_file),
                                ppn=self.ppn, nodes=self.nodes,
                                walltime=self.walltime)
                sub.job(submit=self.submit)

            if self.multiple_samples:
                all_samples_commands.append(sh_command)

        if self.multiple_samples:
            sub = Submitter(all_samples_commands, job_name='miso',
                            sh_filename='miso.qsub.sh',
                            array=True,
                            ppn=self.ppn, nodes=self.nodes,
                            walltime=self.walltime)
            sub.job(submit=self.submit)

    def _write_single_sample(self, bam, sample_id, sh_file):
        commands = []
        commands.append('#!/bin/bash')
        commands.append('# Finding all MISO splicing scores for sample: {}. '
                        'Yay!\n'
                        .format(sample_id))

        event_types = ['SE', 'MXE', 'AFE', 'ALE', 'A3SS', 'A5SS',
                       'RI', 'TANDEMUTR']

        '''
        Get the read length. Gonna keep this as bash because samtools and head are very fast.
        WARNING - this only takes the read length of the first read, not the average read length. 
        This has caused problems in the past if the first read is shorter than the average, for some reason
        it seems like all reads longer than what is inputed as readlen get thrown out. Should be changed to get 
        the average or most abundant read length instead. (9/2/15)
        '''

        if self.read_length is None:
            commands.append(
                "READ_LEN=$(samtools view %s | head -n 1 | cut -f 10 | awk '{ "
                "print length }')" % (bam))
        else:
            commands.append('READ_LEN={}'.format(self.read_length))

        for event_type in event_types:
            out_dir = '{}/miso/{}/{}'.format(os.path.dirname(os.path
                                                             .abspath(bam)),
                                             sample_id, event_type)
            psi_out = '{}/psi.out'.format(out_dir)
            psi_err = '{}/psi.err'.format(out_dir)

            commands.append('\n\n# calculate Psi scores for'
                            ' all {} events'.format(event_type))
            commands.append('mkdir -p {}'.format(out_dir))
            commands.append("miso \
         --run {genome_dir}/{genome}/miso/{event_type}_index \
         {bam} --output-dir {out_dir} \
         --read-len $READ_LEN \
         --settings-filename {6}/hg19/miso_annotations"
                            "/miso_settings_min_event_reads10.txt \
 -p {ppn} \
 > {psi_out} \
 2> {psi_err}".format(genome=self.genome, event_type=event_type, bam=bam,
                out_dir=out_dir, psi_out=psi_out, psi_err=psi_err,
                      genome_dir=os.environ['GENOME'], ppn=self.ppn))

            commands.append("\n# Check that the psi calculation jobs didn't "
                            "fail.\n#'-z' "
                            "returns "
                            "true when a string is empty, so this is checking "
                            "that grepping these files for the words 'failed' "
                            "and 'shutdown' didn't find anything.")
            commands.append('iffailed=$(grep failed {})'.format(psi_out))
            commands.append('ifshutdown=$(grep shutdown {})'.format(psi_err))
            commands.append(
                "if [ ! -z \"$iffailed\" -o ! -z \"$ifshutdown\" ] ; "
                "then\n\
    #rm -rf {0}\n\
    echo \"MISO psi failed on event type: {1}\"\n\
    exit 1\n\
fi\n".format(out_dir, event_type))

            commands.append('# Summarize psi scores for all {} events'
                            .format(event_type))
            commands.append('run_miso.py '
                            '--summarize-samples {0} ' \
                            '{0} >{0}/summary.out 2>{0}/summary.err'.format(
                out_dir))
            commands.append("\n# Check that the summary jobs didn't fail")
            commands.append("# '-s' returns true if file size is nonzero, "
                            "and the error file should be empty.")
            commands.append("""if [ -s {0}/summary.err ] ; then
    #rm -rf {0}\n
    echo 'MISO psi failed on event type: {1}'
    exit 1
fi
""".format(out_dir, event_type))

        with open(sh_file, 'w') as f:
            f.write('\n'.join(commands))
        sys.stdout.write('Wrote miso script for sample "{}": {}\n'.format(
            sample_id, sh_file))


# Function: main
def main():
    '''
    This function is invoked when the program is run from the command line,
    i.e. as:
        python submit_miso_pipeline.py
    or as:
        ./submit_miso_pipeline.py
    If the user has executable permissions on the user (set by chmod ug+x
    program.py or by chmod 775 program py. Just need the 4th bit set to true)
    '''
    cl = CommandLine()
    try:
        submit = not cl.args['do_not_submit']

        MisoPipeline(cl.args['bam'],
                     cl.args['sample_info'],
                     cl.args['sample_id'],
                     cl.args['output_sh'],
                     cl.args['genome'],
                     cl.args['walltime'],
                     cl.args['nodes'],
                     cl.args['ppn'],
                     read_length=cl.args['read_length'],
                     submit=submit)

    # If not all the correct arguments are given, break the program and
    # show the usage information
    except Usage, err:
        cl.do_usage_and_die(err.msg)


if __name__ == '__main__':
    main()
