import urllib.request
import urllib
import requests
import xml.etree.ElementTree as ET

# this is a template for a URL that looks like:
# http://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=24818216&retmode=xml
PUB_MED_XML_SVC_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={0}&retmode=xml'
# SRP IMPLEMENTATION
SRP_ELINK_URL = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&db=sra&cmd=neighbor&id=%s'
SRP_EFETCH_URL = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=sra&retttype=acc&id=%s'


def get_pubmed_info(pub_med_id):
    resp = requests.get(PUB_MED_XML_SVC_URL.format(pub_med_id))
    if resp.status_code == 200:
        root = ET.fromstring(resp.text.encode('utf-8'))

        pubmed_info = dict()

        def add_if_some_val(name, val):
            if val is not None:
                pubmed_info[name] = val

        add_if_some_val('pub_title', root.findtext('.//ArticleTitle'))
        add_if_some_val('pub_abstract', root.findtext('.//AbstractText'))
        add_if_some_val('pub_journal', root.findtext('.//Journal/Title'))
        add_if_some_val('pub_volume', root.findtext('.//Volume'))
        add_if_some_val('pub_pages', root.findtext('.//MedlinePgn'))

        pub_date_node = root.find('.//PubDate')
        if pub_date_node is not None:
            add_if_some_val('pub_year', pub_date_node.findtext('Year'))
            add_if_some_val('pub_month', pub_date_node.findtext('Month'))
            add_if_some_val('pub_day', pub_date_node.findtext('Day'))

        def auth_node_to_str(auth_node):
            name_parts = []

            f_name = auth_node.findtext('ForeName')
            if f_name:
                name_parts.append(f_name)
            else:
                init = auth_node.findtext('Initials')
                if init:
                    name_parts.append(init)

            l_name = auth_node.findtext('LastName')
            if l_name:
                name_parts.append(l_name)

            return ' '.join(name_parts)

        author_list_node = root.find('.//AuthorList')
        if author_list_node is not None:
            authors = ', '.join(map(auth_node_to_str, author_list_node.findall('.//Author')))
            if authors:
                try:
                    if author_list_node.attrib['CompleteYN'] == 'N':
                        authors += ' et al.'
                except KeyError:
                    pass

                pubmed_info['pub_authors'] = authors

        # make sure some required fields are here
        # I've found some pubmed ids don't have this information
        if 'pub_volume' not in pubmed_info:
            pubmed_info['pub_volume'] = None
        if 'pub_pages' not in pubmed_info:
            pubmed_info['pub_pages'] = None

        ## This function should add the pubmed ID to the object as well,
        ## otherwise the batch uploader may fail
        pubmed_info['pub_pubmed'] = pub_med_id

        return pubmed_info
    else:
        raise Exception('unexpected response status code from pubmed service: {0}'.format(resp.status_code))

# SRP IMPLEMENTATION
def get_SRP(pub_med_id):
    resp = urllib.request.urlopen(SRP_ELINK_URL % pub_med_id).read()
    response_root = ET.fromstring(resp)
    elink= ''
    for line in response_root:
        ID = line.find('LinkSetDb')
        if ID != None:
            for link in ID.findall('Link'):
                elink = link.find('Id').text
    resp2 = urllib.request.urlopen(SRP_EFETCH_URL % elink).read()
    response_root2 = ET.fromstring(resp2)
    SRP = ''
    for line in response_root2:
        ID =  line.find('STUDY')
        if ID != None:
            SRP = ID.find('IDENTIFIERS').find('PRIMARY_ID').text

    return SRP
# END SRP IMPLEMENTATION

# run a little test code if this is the main module
if __name__ == '__main__':
    def print_pubmed_info(pubmed_id):
        print('')
        print('=====================================================================================')
        print(pubmed_id)
        print(PUB_MED_XML_SVC_URL.format(pubmed_id))
        for k, v in get_pubmed_info(pubmed_id).items():
            print('-------')
            print(k)
            print(v)

    print_pubmed_info(17172759)
    print_pubmed_info(24818216)
    print_pubmed_info(16214803)
