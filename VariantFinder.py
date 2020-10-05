# Author: Sam Shenoi
# Description: This file implements the variant mapping algorithm
#  in order to find similiar variant sets
#
#
# Algorithm Flow:
#   1. Calculate KS test on the chromosome distributions of the variant sets
#   2. Filter out results with high pvalue depending on threshold
#   3. Convert Variant to Gene
#   4. Preform Variant to Gene Mapping
#   5. Filter resulting set
#   6. Return values


# Imports
import copy
import re
import vcf
import numpy as np
import os
import glob
import matplotlib.pyplot as plt
from ndtest import ks2d2s
from datagen import VCFGen
import random
import subprocess
import json



class RecordPersist:
    def __init__(self,CHROM,POS,REF,ALT):
        self.CHROM = CHROM
        self.POS = POS
        self.REF = REF
        self.ALT = ALT
        self.accessions = dict()

        for i in range(1,86-63):
            self.accessions["CM0006" + str(63 + i -1) + ".2"] = i
        self.accessions["CM000685.2"] = 23
        self.accessions["CM000686.2"] = 24

        self.accessions["NC_000001.11"] = 1
        self.accessions["NC_000002.12"] = 2
        self.accessions["NC_000003.12"] = 3
        self.accessions["NC_000004.12"] = 4
        self.accessions["NC_000005.10"] = 5
        self.accessions["NC_000006.12"] = 6
        self.accessions["NC_000007.14"] = 7
        self.accessions["NC_000008.11"] = 8
        self.accessions["NC_000009.12"] = 9
        self.accessions["NC_000010.11"] = 10
        self.accessions["NC_000011.10"] = 11
        self.accessions["NC_000012.12"] = 12
        self.accessions["NC_000013.11"] = 13
        self.accessions["NC_000014.9"] = 14
        self.accessions["NC_000015.10"] = 15
        self.accessions["NC_000016.10"] = 16
        self.accessions["NC_000017.11"] = 17
        self.accessions["NC_000018.10"] = 18
        self.accessions["NC_000019.10"] = 19
        self.accessions["NC_000020.11"] = 20
        self.accessions["NC_000021.9"] = 21
        self.accessions["NC_000022.11"] = 22
        self.accessions["NC_000023.11"] = 23  # Treat X as 23
        self.accessions["NC_000024.10"] = 24   # Treat Y as 24
        self.accessions["X"] = 23
        self.accessions["Y"] = 24

        self.accessions["NT_113889.1"] = 1

    def __eq__(self,obj):
        isEqual = False
        if obj.CHROM == self.CHROM and obj.POS == self.POS and obj.REF == self.REF and obj.ALT == self.ALT:
            isEqual = True
        return isEqual
    def __neq__(self,obj):
        return not self.__eq__(obj)


    def __hash__(self):
        code = {
            "A" : 0,
            "G" : 1,
            "C" : 2,
            "T" : 3
        }

        intChrom = self.accessions[self.CHROM]
        intPos = int(self.POS)
        intREF = code[self.REF]
        #test = self.ALT[0]
        #print(test)
        #intALT = code[test]

        return intChrom#intPos * 1000 + intChrom * 100 + intREF * 10 #+ intALT



# Variant Finder Class
class VariantFinder:
    def __init__(self):

        self.accessions = dict()
        random.seed()

        for i in range(1,86-63):
            self.accessions["CM0006" + str(63 + i -1) + ".2"] = i
        self.accessions["CM000685.2"] = 23
        self.accessions["CM000686.2"] = 24

        self.accessions["NC_000001.11"] = 1
        self.accessions["NC_000002.12"] = 2
        self.accessions["NC_000003.12"] = 3
        self.accessions["NC_000004.12"] = 4
        self.accessions["NC_000005.10"] = 5
        self.accessions["NC_000006.12"] = 6
        self.accessions["NC_000007.14"] = 7
        self.accessions["NC_000008.11"] = 8
        self.accessions["NC_000009.12"] = 9
        self.accessions["NC_000010.11"] = 10
        self.accessions["NC_000011.10"] = 11
        self.accessions["NC_000012.12"] = 12
        self.accessions["NC_000013.11"] = 13
        self.accessions["NC_000014.9"] = 14
        self.accessions["NC_000015.10"] = 15
        self.accessions["NC_000016.10"] = 16
        self.accessions["NC_000017.11"] = 17
        self.accessions["NC_000018.10"] = 18
        self.accessions["NC_000019.10"] = 19
        self.accessions["NC_000020.11"] = 20
        self.accessions["NC_000021.9"] = 21
        self.accessions["NC_000022.11"] = 22
        self.accessions["NC_000023.11"] = 23  # Treat X as 23
        self.accessions["NC_000024.10"] = 24   # Treat Y as 24
        self.accessions["X"] = 23
        self.accessions["Y"] = 24

        self.accessions["NT_113889.1"] = 1


        self.chrom_size = {
            1: 248956422,
            2: 242193529,
            3: 198295559,
            4: 190214555,
            5: 181538259,
            6: 170805979,
            7: 159345973,
            8: 145138636,
            9: 138394717,
            10: 133797422,
            11: 135086622,
            12: 133275309,
            13: 114364328,
            14: 107043718,
            15: 101991189,
            16: 90338345,
            17: 83257441,
            18: 80373285,
            19: 58617616,
            20: 64444167,
            21: 46709983,
            22: 50818468,
            23: 156040895,
            24: 57227415
        }


    def pull_variant_set_distributions(self,folder):
        # This would be where the variant sets would be pulled.
        # For now I'll just open up some vcf files
        chroms = []
        records = []
        file_names = []
        for file_name in glob.glob(folder +"/*.vcf"):
            chrom, record = self.vcf_read_file(file_name)
            chroms.append(chrom)
            records.append(record)
            file_names.append(file_name)

        return chroms, records,file_names

    def getXY(self,chrom):
        x = []
        y = []

        for i in range(1,15):
            x.append(i)
            if i in chrom.keys():
                y.append(chrom[i])
            else:
                y.append(0)
        return x,y


    def random_file_from_chroms(self,records):
        full_records = []
        for r in records:
            for z in r:
                full_records.append(z)
        d = VCFGen()

        random.shuffle(full_records)

        num_files = 20
        d.run(num_files,full_records,"Test1")



    def vcf_read_file(self,filename):
        # Create a dictionary for the chromsomes
        chrom = dict()
        records = []
        # Open the VCF file
        vcf_reader = vcf.Reader(open(filename, 'r'))

        # For each record in the VCF file save it
        for record in vcf_reader:

            records.append(RecordPersist(record.CHROM,record.POS,record.REF,record.ALT))
            # Convert the chromsome to an appropriate number if references index
            c = self.chrom_conversions(record.CHROM)

            #if self.chrom_size[c]/2 < record.POS:
            #    c = c + .5



            # Count the number of chromosomes
            if c in chrom.keys():
                chrom[c] = chrom[c] + 1
            else:
                chrom[c] =  1

        return chrom, records

    def plot_graph(self,x,y,filename):
        plt.plot(x, y)
        plt.savefig(filename)


    def run(self,filename,folder,outfile):
        # First for the VCF file we are using,
        # read the file and calculate chromosome distribtions
        chrom,record = self.vcf_read_file(filename)

        our_x,our_y = self.getXY(chrom)

        #self.plot_graph(our_x,our_y,"./plots/original.png")

        # ##### Call the database to find other variant sets ######
        chroms, records, file_names = self.pull_variant_set_distributions(folder)

        # Loop through resulting variants sets and preform the KS test

        outfile = open(outfile,'w')

        print("Read complete")
        for count in range(0,len(chroms)):
            x,y = self.getXY(chroms[count])
            #self.plot_graph(x,y,"./plots/case%i.png"%(count))
            p = ks2d2s(np.asarray(our_x), np.asarray(our_y), np.asarray(x), np.asarray(y))
            jaccard= self.Jaccard(record,records[count],"%s%s" %(filename,file_names[count]))

            outfile.write("%s\t%s\t%f\t%s\n" %(filename,file_names[count],p,jaccard))

            print(count/len(chroms))

        outfile.close()



    def test(self,infile,outfile):
        f_in = open(infile, "r")
        f_out = open(outfile, "w")

        true_pos = 0
        false_pos = 0
        true_neg = 0
        false_neg = 0

        # ignore first line
        f_in.readline()

        # check each row
        for line in f_in.readlines():
            line  = line.rstrip()
            colums = line.split("\t")
            if float(colums[2]) > 0.01:
                if float(colums[3]) > 0.5:
                    true_pos += 1
                    line += "\t" + "TP"
                else:
                    false_pos += 1
                    line += "\t" + "FP"
            else:
                if float(colums[3]) > 0.5:
                    false_neg += 1
                    line += "\t" + "FN"
                else:
                    true_neg += 1
                    line += "\t" + "TN"
            line += "\n"
            f_out.write(line)

        accuracy = float(true_pos+true_neg)/(true_pos+true_neg+false_pos+false_neg)

        true_positive_rate = true_pos/float(true_pos+false_neg)
        true_negative_rate = true_neg/float(true_neg+false_pos)
        balanced_accuracy = (true_positive_rate + true_negative_rate)/2

        f_in.close()
        f_out.close()
        return accuracy,balanced_accuracy

    def write_c_files(self,records1,records2,runname):
        runname = re.sub("\./randomfiles/","",runname)

        runname = re.sub("\./testdata/","",runname)
        f1 = open("./binarytest/%sfile1.txt" %(runname),'w')
        for r in records1:
            f1.write("%s\t%s\t%s\t%s\n" %(self.chrom_conversions(r.CHROM),r.POS,r.REF,r.ALT[0]))
        f1.close()

        f2 = open("./binarytest/%sfile2.txt" %(runname),'w')
        for r in records2:
            f2.write("%s\t%s\t%s\t%s\n" %(self.chrom_conversions(r.CHROM),r.POS,r.REF,r.ALT[0]))
        f2.close()



    def Jaccard(self,records1,records2,runname):
        # Run the Jaccard similiarity between the two variant sets

        # First re-extract the data from the files. Ensures no contaiminatio

        # Calculate Jaccard coefficient
        #intersect = len(set.intersection(set(records1),set(records2)))
        write_c_files(records1,records2,runname)

        args = ("./a.out", "./binarytest/%sfile2.txt" %(runname),"./binarytest/%sfile1.txt" %(runname),runname)
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, text=True, encoding="utf-8")

        output = proc.stdout.read()


        #err = proc.stderr.read()


        # Return similarity coefficient
        return output#, intersect/(len(records1) + len(records2) - intersect)


    # Use the versions as of 9/17/2020. Update this later
    #   for database conversion call
    def chrom_conversions(self,chrom):
        out = chrom
        if not chrom.isnumeric():
            out = self.accessions[chrom]
        return out

    # UPGMA
    # Adaption from: https://github.com/lex8erna/UPGMApy/blob/master/UPGMA.py
    # preconditions:
    #     - records: a list of chrom1 variant lists
    #
    def UPGMA(self,records,filenames):
        # Create the distance matrix from the records
        dm = self.distance_matrix(records)

        # There will always be 2n-1 nodes created as a result of UPGMA
        parents = [-1] * (len(filenames)*2 - 1)
        counter = 0
        nodes = [i for i in range(0,len(filenames))]
        max_node = len(filenames)

        string_rep = copy.deepcopy(filenames)

        # While we still have nodes to do
        while(counter < len(filenames) - 1):
            # Get the smallest x and y values from the distance matrix
            smallest_x,smallest_y = self.getsmallest(dm)

            ndx = min(smallest_x,smallest_y)
            large_ndx = max(smallest_x,smallest_y)

            parents[nodes[smallest_x]] = max_node
            parents[nodes[smallest_y]] = max_node
            nodes[ndx] = max_node
            max_node = max_node + 1
            del nodes[large_ndx]

            # Get a string representation of the tree
            string_rep[ndx] = "(" + string_rep[ndx] + " | " + string_rep[large_ndx] + ")"
            del string_rep[large_ndx]


            # Update the distance matrix
            dm = self.distance_matrix_update(dm,smallest_x,smallest_y)

            counter = counter + 1

        return parents,string_rep[0]

    def print_matrix(self,dm):
        for d in dm:
            print(d)
        print()
    #
    def distance_matrix_update(self,dm,smallest_x,smallest_y):

        # Everything before the smallest row should be the same
        smallest_row = min(smallest_x,smallest_y)
        larger_row = max(smallest_x,smallest_y)

        joined_node = []
        for i in range(0,smallest_row):
            joined_node.append((dm[smallest_row][i] + dm[larger_row][i])/2)
        dm[smallest_row] = joined_node

        # Now replace all of the first row
        for i in range(smallest_row +1,larger_row):
            dm[i][smallest_row] = (dm[i][smallest_row] + dm[larger_row][i])/2

        # Now replace all of the first row
        for i in range(larger_row +1,len(dm)-1):
            dm[i][smallest_row] = (dm[i][smallest_row] + dm[i][larger_row])/2

            del dm[i][larger_row]
        del dm[larger_row]

        return dm

    def getsmallest(self,dm):
        smallest_x = len(dm) -1
        smallest_y = 0
        smallest_n = dm[smallest_x][smallest_y]
        for i in range(0, len(dm)):
            for y in range(0,i):
                if dm[i][y] < smallest_n:
                    smallest_n = dm[i][y]
                    smallest_x = i
                    smallest_y = y
        return smallest_x,smallest_y


    def distance_matrix(self,records):
        # Distance matrix formation
        dm = [[]] * len(records)

        for i in range(0,len(records)):
            dm[i] = [0] * (i + 1)
            pos = [(e.POS,e.CHROM) for e in records[i]]
            for y in range(0,i):
                    pos_2 = [ (e.POS,e.CHROM) for e in records[y]]
                    pos_2 = pos_2 + pos
                    dm[i][y] = len(list(dict.fromkeys(pos_2)))
        return dm

    def write_json(self,parents, nodenames):

        obj_list =[]
        for i in range(0,len(parents)):
            obj = dict()
            obj["node_id"] = i
            obj["parent"] = parents[i]
            if i < len(nodenames):
                obj["node_name"] = nodenames[i]
            else:
                obj["node_name"] = ""
            obj_list.append(obj)
        JSON_FILE = open('%s.json' % "test", 'w')
        JSON_FILE.write(json.dumps(obj_list))
        JSON_FILE.close()




if __name__ == "__main__":
    v = VariantFinder()

    # Pull variant set distributions from the randomfiles folder
    chroms, records, file_names = v.pull_variant_set_distributions("./randomfiles")

    parents, string_rep = v.UPGMA(records,file_names)

    v.write_json(parents,file_names)

    f = open("stringrep.json",'w')
    test = dict()
    test["value"] = string_rep
    test["id"] = 1
    f.write(json.dumps(test))
    f.close()

    #chrom, records = v.vcf_read_file("randomfiles/VCFTestTest110.vcf")
    #chrom2, records2 = v.vcf_read_file("randomfiles/VCFTestTest1Pt20.vcf")

    #d = VCFGen()

    #v.write_c_files(records,records2,"Chrom2Chrom4")



    #chroms,records,file_names = v.pull_variant_set_distributions("./randomfiles/")
    #print(v.Jaccard("./testdata/chrom1.vcf","./testdata/chrom1.vcf"))
    #v.run("chrom1.vcf","./randomfiles","chrom_bin.tsv")
    #accuracy,balanced_accuracy = v.test("chrom_bin.tsv","chrom_bin_stats.tsv")
    #print("Accuracy:%s"%(accuracy))
    #print("Balanced Accuracy:%s"%(balanced_accuracy))
    #chroms,records,file_names = v.pull_variant_set_distributions("./testdata/")
    #v.random_file_from_chroms(records)