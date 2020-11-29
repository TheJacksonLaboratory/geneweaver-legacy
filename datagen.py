# Author: Sam Shenoi
# Description: This file generates a bunch of randomly created vcf files
#   in order to test the VariantFinder Algorithm. The data in these vcf
#   files are completely fictional and should not be treated as real info

import random
import vcf

# Adapted From: https://www.programcreek.com/python/?code=phe-bioinformatics%2FPHEnix%2FPHEnix-master%2Fphe%2Fvariant%2F__init__.py
class VCFTemplate(object):

    def __init__(self, vcf_reader):
        self.infos = vcf_reader.infos
        self.formats = vcf_reader.formats
        self.filters = vcf_reader.filters
        self.alts = vcf_reader.alts
        self.contigs = vcf_reader.contigs
        self.metadata = vcf_reader.metadata
        self._column_headers = ['CHROM', 'POS', 'ID', 'REF', 'ALT', 'QUAL', 'FILTER', 'INFO']
        self.samples = "vcf_reader.samples"



class VCFGen:
    def __init__(self):
        self.chromosomes = list(range(22))
        self.chromosomes.append("X")
        self.chromosomes.append("Y")

        self.letters = ["A","C","G","T"]
        random.seed()

        self.position_size = 500000

        self.base_filename = "./randomfiles/VCFTest"


    def gen_header(self):
        header = '##fileformat=VCFv4.0\n##fileDate=20200915\n'
        header = header + '##source=madeup\n##reference=GRCh38.p7\n'
        header = header + '##phasing=none\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'
        return header

    def create_row(self,id):

        # Get a chromsome
        chrom_number = random.randint(0,len(self.chromosomes) -1)
        chrom = self.chromosomes[chrom_number]

        # Get a chromosome position.
        chrom_pos = random.randint(0,self.position_size)

        # Get a letter for the reference
        ref = self.letters[random.randint(0,len(self.letters) -1)]

        # Get a letter for the alternative. Ensure that alt != ref
        alt = ref
        while alt == ref:
            alt =  self.letters[random.randint(0,len(self.letters) -1)]

        # Set the quality and filter value to .
        qual = filt =  "."

        # Finally return the generated tab delimeted string
        row_record = vcf.model._Record(
            CHROM=chrom_number,
            POS=chrom_pos,
            ID=id,
            REF=ref,
            ALT=alt,
            QUAL=qual,
            FILTER=filt,
            INFO="Sample File For Testing",
            FORMAT="GT:GQ:DP:HQ",
            sample_indexes="12:20:12:92"
            )
        return row_record

    def run(self,num_files,records,run_name):


        # Generate multiple files
        for f in range(0,num_files):

            res = random.sample(records,random.randint(0,len(records)))

            # Write the first one two file
            self.create_file("%s%i"%(run_name,f),res)

            random.shuffle(res)

            # Shuffle Rows and write that to file
            self.create_file("%s%i:%s"%(run_name,f,"SHUFFLED"),res)

            # Get 20% of list size
            self.create_file("%s%i:%s"%(run_name,f,"20%"),random.sample(res,int(len(res) * .2)))

            # Get 40% of list size
            self.create_file("%s%i:%s"%(run_name,f,"40%"),random.sample(res,int(len(res) * .4)))

            # Get 60% of list size
            self.create_file("%s%i:%s"%(run_name,f,"60%"),random.sample(res,int(len(res) * .6)))

            # Get 80% of list size
            self.create_file("%s%i:%s"%(run_name,f,"80%"),random.sample(res,int(len(res) * .8)))

    def create_file(self,run,records):
        # Use the headers from the previous filename for this filename. Hack for now
        template = VCFTemplate(vcf.Reader(filename="./testdata/chrom6.vcf"))
        outfile = open("%s%s.vcf" %(self.base_filename,run),"w")
        outfile.write(self.gen_header())
        count = 1
        for r in records:
            alt = r.ALT[0]
            outfile.write("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" %(r.CHROM,r.POS,str(count),r.REF,alt,".",".","."))
            count = count + 1


if __name__ == "__main__":
    vgen = VCFGen()
    vgen.run(1000000,5)




















