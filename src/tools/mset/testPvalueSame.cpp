/*
testPvalueSame.cpp: ...
Created: Sun Sep 11 18:47:33 CDT 2016
TODO: unit test unique function
      test full program against mset.R
*/
#include <fstream>
#include <iostream>
#include <algorithm>
#include <set>
#include <vector>
#include <cstdlib>
#include <ctime>
using namespace std;


//without replacement
void sample(vector<string>& sampleInto,vector<string>& from,vector<unsigned long>& ndxs){
    random_shuffle(ndxs.begin(),ndxs.end());
    for(unsigned long i=0;i<sampleInto.size();i++){
        sampleInto[i]=from[ndxs[i]];//copy the random element
    }
}

//gets the size of the intersection between the two ranges defined by the four
//iterators
//modified from cplusplus.com algorithm's set_intersection
template<typename Iter1,typename Iter2>
int intersectSize(Iter1 first1,Iter1 last1,
                  Iter2 first2,Iter2 last2){
    int toReturn=0;
    while(first1!=last1 && first2!=last2){
        if(*first1<*first2) first1++;
        else if (*first2<*first1) first2++;
        else{
            toReturn++;
            first1++;
            first2++;
        }
    }
    return toReturn;
}

//if its not in the set, add it to the return vector
//and the set
//
//allows returned vector to have unique elements in the same order as the
//original
vector<string> unique(vector<string>& toUnorderedSet){
    set<string> checkWith;
    vector<string> toReturn;
    for(unsigned int i=0;i<toUnorderedSet.size();i++){
        if(checkWith.find(toUnorderedSet[i])==checkWith.end()){
            checkWith.insert(toUnorderedSet[i]);
            toReturn.push_back(toUnorderedSet[i]);
        }
    }
    return toReturn;
}


void printVec(vector<string>& v){
    for(unsigned int i=0;i<v.size();i++){
        cout<<" "<<v[i];
    }
    cout<<endl;
}
/*
int main(int argc, char** argv){
    vector<string> makeUnique{"z","a","n","a","a","n","f","j"};
    vector<string> expected{"z","a","n","f","j"};
    vector<string> result=unique(makeUnique);
    cout<<"input"<<endl;
    printVec(makeUnique);
    cout<<"output"<<endl;
    printVec(result);
    cout<<"expected"<<endl;
    printVec(expected);
    
    return 0;
}
/*/
int main(int argc, char** argv){
    srand(time(0));

    set<string> setOfInterest;
    set<string> top;
    vector<string> background;


    string bgFilename;
    cout<<"enter filename for background:>";
    cin>>bgFilename;

    string interestFilename;
    cout<<"enter filename for list of interest:>";
    cin>>interestFilename;

    ifstream readLists(bgFilename.c_str());

    string inputStr;
    while(readLists>>inputStr){
        if(inputStr!="---"){
            background.push_back(inputStr);//read into sets so they're unique
        }
    }
    readLists.clear();
    readLists.close();
    readLists.open(interestFilename.c_str());

    while(readLists>>inputStr){
        if(inputStr!="---"){
            setOfInterest.insert(inputStr);
        }
    }

    readLists.clear();
    readLists.close();

    int topResults=0;
    cout<<"enter number of top results:>";
    cin>>topResults;

    //copy that number from background into top, converting to set in the
    //process
    for(vector<string>::iterator i=background.begin(); distance(background.begin(),i)<topResults;i++){
        top.insert(*i);
    }

    vector<unsigned long> randomizedBackgroundNdxs;
    for(unsigned long i=0;i<background.size();i++){
        randomizedBackgroundNdxs.push_back(i);
    }
        
        

    int numSamples=0;
    cout<<"enter number of samples:>";
    cin>>numSamples;


    //the length of the intersect with the top set and the intrest set to
    //compare to the simulations
    int checklength=intersectSize(top.begin(),top.end(),setOfInterest.begin(),setOfInterest.end());

    vector<string> sampledSet(top.size());

    cout<<"everything is read"<<endl;
    int numGreater=0;
    for(int i=0;i<numSamples;i++){
        sample(sampledSet,background,randomizedBackgroundNdxs);//sample sampledSet.size elements from background into sampledSet without replacement

        if(intersectSize(sampledSet.begin(),sampledSet.end(),setOfInterest.begin(),setOfInterest.end())>checklength){
            //if the size of the intersect of sampledSet and setOfInterest> the checklength intersect from before
            numGreater++;//increment the count
        }
    }

    double pvalue=((double)numGreater)/((double)numSamples);

    cout<<"pvalue: "<<pvalue<<endl;
    cout<<"number with at least as many matches as actual: "<<numGreater<<endl;

    return 0;
}
//*/
