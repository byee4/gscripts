#!/usr/bin/env python

import argparse
import numpy as np
import os
import shlex
import subprocess

from gscripts.qtools import Submitter

"""Original script
from gscripts.qtools import Submitter
import numpy as np
import math


downsample_command = 'java -jar /projects/ps-yeolab/software/picard-tools-1.93/DownsampleSam.jar'

iter_per_downsample = 10


#initial_command_list = [#"DIR=/home/obotvinnik/scratch/mn_diff_singlecell/fastq/downsample",
#                "BAM=/home/obotvinnik/scratch/mn_diff_singlecell/fastq/P9_1.bam"]
input_bam = "/home/obotvinnik/scratch/mn_diff_singlecell/fastq/P9_1.Aligned.out.sam.bam.sorted.bam"

#downsample_dir = '~/projects/singlecell/data/round1/downsampling'
command_list = []
for downsample_prob in np.arange(0.01, 1, 0.01):
    for i in range(iter_per_downsample):
        out_bam = 'P9_1_prob{}_iter{}.bam'.format(downsample_prob, i)
        random_seed = 2014 + i
        command_list.append(
            '{} INPUT={} OUTPUT={} RANDOM_SEED={} PROBABILITY={} CREATE_INDEX=true'.format(downsample_command,
                                                                           input_bam,
                                                                           out_bam,
                                                                           random_seed,
                                                                           downsample_prob))
job_name = 'downsample'
sub = Submitter(sh_file='downsample.sh', queue_type='PBS',
                command_list=command_list, job_name=job_name, walltime='4:00:00')
sub.write_sh(submit=True, nodes=1, ppn=1, queue='home', array=True, max_running=20)


"""


class CommandLine(object):
    def __init__(self, inOpts=None):
        self.parser = parser = argparse.ArgumentParser(
            description='Downsample (millions of) reads from a bam file')
        bam = parser.add_mutually_exclusive_group(required=True)
        bam.add_argument('--bam',
                         type=str, action='store',
                         help='Bam file to downsample')
        bam.add_argument('--sample-info',
                         type=str, action='store',
                         help='A file containing names of bam files to '
                              'downsample on separate lines, '
                              'and tab-separated with sample ids (no '
                              'header), e.g.:'
                              'sample1.bam\\tcontrol\\n'
                              'sample2.bam\\ttreatment\\n')
        parser.add_argument('--sample-id', type=str, action='store',
                            help='Sample ID to prefix the output bam files'
                                 '. Required if providing a single bam '
                                 'file.')
        parser.add_argument('-t', '--iter-per-downsample',
                            type=int, action='store', default=3,
                            help='For each downsampling level, how many '
                                 'iterations to perform')

        parser.add_argument('--min-reads', type=float, action='store',
                            default=1,
                            help='Minimum number of reads to downsample.')
        parser.add_argument('--max-reads', type=float, action='store',
                            help='Maximum number of reads to downsample. '
                                 'Helpful if you have a sample with 100 '
                                 'million reads but you only want to '
                                 'downsample every 1 million read up to 25 '
                                 'million reads. If not specified, then up to '
                                 'the maximum number of reads in the bam file')

        parser.add_argument('--reads-multiplier', type=float, action='store',
                            default=1e6,
                            help='What to multiply the read numbers by. '
                                 'Assumes that you want to downsample by '
                                 'millions of reads.')
        parser.add_argument('-s', '--step-size', type=float, action='store',
                            default=1,
                            help='Step size of # of reads to downsample, '
                                 'default is 1 (million) reads, so you end up '
                                 'with 1 million, 2 million, 3 million '
                                 'downsampled reads')

        parser.add_argument('-r', '--random-seed-base', type=int,
                            action='store', default=2014,
                            help='To make sure this exact downsampling is '
                                 'reproducible but still random for different '
                                 'iterations, use this value + iteration '
                                 'number as the random seed.')
        parser.add_argument('-j', '--jar',
                            default="/projects/ps-yeolab/software/picard-tools-1.93/DownsampleSam.jar",
                            type=str, action='store',
                            help='The Java Archive from PicardTools to use')
        parser.add_argument('-o', '--out-dir', type=str,
                            action='store', default='./',
                            help='Where you want to save the downsampled bams'
                                 '. Default is the current directory.')
        parser.add_argument('-n', '--name', default='downsample',
                            action='store', type=str,
                            help='The name of the submitted job in the queue')
        parser.add_argument('--out-sh', action='store', type=str,
                            required=False,
                            help='The sh file written and submitted to the '
                                 'cluster. Default is the name of the job + "'
                                 '.sh"')
        parser.add_argument('--do-not-submit', required=False,
                            action='store_true', default=False,
                            help='Flag to not actually submit the job but '
                                 'just write the sh file (for testing)')
        parser.add_argument('--queue-type', required=False, type=str,
                            action='store', default='PBS',
                            help='Type of the queue to submit to. For testing '
                                 'purposes on non-server devices, e.g. laptops')
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


# Class: Downsample
class Downsample(object):
    def __init__(self, bams, sample_ids, jar, iter_per_percentage,
                 min_reads, max_reads, step_size, reads_multiplier,
                 random_seed_base, out_dir, name, out_sh=None, submit=True,
                 queue_type='PBS'):
        """Any CamelCase here is directly copied from the STAR inputs for
        complete compatibility
        """
        # Make the directory if it's not there already
        try:
            os.mkdir(out_dir)
        except OSError:
            pass

        downsample_command = 'java -jar {}'.format(jar)

        commands = []
        for bam, sample_id in zip(bams, sample_ids):
            flagstat = 'samtools flagstat {}'.format(bam)
            p = subprocess.Popen(shlex.split(flagstat),
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            out, err = p.communicate()
            n_read1 = float(out.split('\n')[4].split()[0]) / reads_multiplier

            vmin = min_reads
            vmax = n_read1 if max_reads is None else max_reads

            for reads in np.arange(vmin, vmax, step_size):
                downsample_prob = reads / n_read1
                for i in range(iter_per_percentage):
                    out_bam = '{}_{:.1e}reads_iter{}.bam'.format(sample_id,
                                                                 reads, i)
                    random_seed = random_seed_base + i
                    commands.append(
                        '{} INPUT={} OUTPUT={} RANDOM_SEED={} PROBABILITY={} CREATE_INDEX=true'.format(
                            downsample_command,
                            bam,
                            out_bam,
                            random_seed,
                            downsample_prob))

        sub = Submitter(sh_filename=out_sh, queue_type=queue_type,
                        commands=commands, job_name=name,
                        walltime='1:00:00', nodes=1, ppn=1, queue='home',
                        array=True,
                        max_running=20)
        sub.write_sh(submit=submit)


if __name__ == '__main__':
    try:
        cl = CommandLine()

        job_name = cl.args['name']
        out_dir = cl.args['out_dir']
        out_sh = name = job_name + '.sh' if cl.args['out_sh'] is None \
            else cl.args['out_sh']
        submit = not cl.args['do_not_submit']
        queue_type = cl.args['queue_type']

        bam = cl.args['bam']
        sample_id = cl.args['sample_id']
        if bam is not None and sample_id is None:
            raise ValueError('If "--bam" is provided, "--sample-id" is also '
                             'required.')

        if cl.args['sample_info'] is not None:
            bams = []
            sample_ids = []
            with open(cl.args['sample_info']) as f:
                for line in f:
                    line = line.strip().split()
                    bams.append(line[0])
                    sample_ids.append(line[1])
        else:
            bams = [bam]
            sample_ids = [sample_id]

        min_reads = cl.args['min_reads']
        max_reads = cl.args['max_reads']
        reads_multiplier = cl.args['reads_multiplier']

        jar = cl.args['jar']
        iter_per_percentage = cl.args['iter_per_downsample']
        step_size = cl.args['step_size']
        random_seed_base = cl.args['random_seed_base']

        Downsample(bams, sample_ids, jar, iter_per_percentage,
                   min_reads, max_reads, step_size, reads_multiplier,
                   random_seed_base, out_dir, name, out_sh, submit, queue_type)

    except Usage, err:
        cl.do_usage_and_die()