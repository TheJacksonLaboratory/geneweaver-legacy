# Author: Sam Shenoi
# Description: This program converts the Geneweaver JSON output format for the HISim into a format that
# can be used by the vz transit graph subway plots

import simplejson
import re


class JSON2TSV:
    def load(self, s):
        #json_file = open(filename,"r")
        #s = str(json_file.read())
        # Clean up the geneweaver json data do that it works correctly

        # First change all ' to "
        s = re.sub("'","\"",s)

        # REGEX has failed me so just loop through the string and convert the apostrophes back
        s = list(s)
        for i in range(1, len(s) -1):
            if s[i] == "\"" and s[i-1].isalnum() and s[i+1].isalnum():
                s[i] = "'"
        s = "".join(s)

        # Doesnt work for some reason: Then convert all of the previous ' that were apostrophes, back to apostrophes
        #s = re.sub(r'([A-Za-z])"s',"\1\'s",s)

        data = simplejson.loads(s)
        return data['nodes']

    
    def generate_graph(self,filename, data):
        
        # Don't get the file extension for the filename
        filename = filename.split(".")[0]
        # Open the nodes file
        nodes = "" #open(filename+"-nodes.tsv","w")
        nodes += "layer\tnode_id\tgenes\tgenesets\n"
        #nodes.write("FILES\t" + filename + "\n") 
        # After doing all of that, figure out what the edges are
        edges = ""# open(filename + "-edges.tsv","w")
        edges += "node_from\tnode_to\n"

        # Loop through all of the nodes
        split = 1
        for i in range(0,len(data)):
            # Write each gene to the file
            genes = data[i]["Genes"]
            genestring = ""
            for g in genes:
                genestring = genestring + ";" + g
            clean_data = re.sub("\n"," ",data[i]["name"])
            nodes += str(data[i]["depth"])+"\t"+str(i) + "\t"+genestring+"\t"+clean_data+"\n"
            #Write the edges
            childs = data[i]["children"]
            for c in childs:
                edges += str(data[i]["id"])+"\t"+str(c)+"\n"
        # Close the file
        #nodes.close()
        #edges.close()
        return nodes, edges 
   






