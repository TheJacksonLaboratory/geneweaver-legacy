//Notes:
//
// Initially borrowed from http://bl.ocks.org/mbostock/1093130
//      with heavy modification. Creates a DAG and displays it in a tree
//      shaped manner, where each child node can have multiple parents, and each
//      non-leaf is collapsible.
//Notes:
// * Each dom element is using
//   children to store refs to expanded children
//   _children to store refs to collapsed children


//root
var g = {
    data: null,
    force: null
};


//initializa
$(function () {

    //use a global var for the data:
    g.data = data;
    /*
     var data = (function () {
     var json = null;
     $.ajax({
     "async": false,
     "global": false,
     "url": "../../../../results.TestOutput.hisim.json",
     "dataType": "json",
     "success": function (data) {
     json = data;
     }
     });
     return json;
     } );
     */

    console.log("DATA = " + JSON.stringify(data));
    var width = 1200,
        height = 1000;

    var r = 6,
        fill = d3.scale.category20();

    var diagonal = d3.svg.diagonal()
        .projection(function (d) {
            return [d.y, d.x];
        });


    //Create a sized SVG surface within viz:
    var svg = d3.select("#viz2")
        .append("svg")
        .attr("width", width)
        .attr("height", height);

    g.link = svg.selectAll("path.link"),
        g.node = svg.selectAll(".node");


    //Create a graph layout engine:
    g.force = d3.layout.force()
        .nodes(g.data.nodes)
        .links(getLinks(g.data.nodes))
        .linkDistance(function (link) {
            //console.log("LINK DISTANCE OUTPUT HERE: " + JSON.stringify(link));
            //return 50;
            return ((link.target.depth - link.source.depth) * 40);
        })
        .linkStrength(function (link) {
            return 1 / ((link.target.depth - link.source.depth) * 1.5);
        })
        .charge(function (d) {
            return (-((d.depth+1) * 400));
        })
        .chargeDistance(300)
        .gravity(0.05)
        .size([width, height])
        .on("tick", tick);


    //Initialize positions of tree elements to reduce tangling caused by random initialization
    nodes = flatten(g.data.nodes);
    var nextdepths = [0];
    for (i = 0; i < nodes.length; i++) {
        while (nodes[i].depth > nextdepths.length - 1) {
            nextdepths.push(0);
        }
        nodes[i].x = nodes[i].depth * 100 + 100;
        nodes[i].y = nextdepths[nodes[i].depth] * 20 + 100;
        nextdepths[nodes[i].depth]++;
    }


    //Draw the graph:
    //Note that this method is invoked again
    //when clicking nodes:
    update();


});


//invoked once at the start,
//and again when from 'click' method
//which expands and collapses a node.

function update() {
    var width = 960,
        height = 500,
        padding = 15;

    //iterate through original nested data, and get one dimension array of nodes.
    var nodes = flatten(g.data.nodes);
    console.log(nodes.length + " nodes to draw");


    //Each node extracted above has a children attribute.
    //from them, we can use a tree() layout function in order
    //to build a links selection.

    var links = getLinks(nodes);


    // pass both of those sets to the graph layout engine, and restart it
    g.force.nodes(nodes)
        .links(links)
        .start();
    //-------------------
    // create a subselection, wiring up data, using a function to define
    //how it's supposed to know what is appended/updated/exited

    //console.log("G.LINK (before): \n" + JSON.stringify(g.link));

    g.link = g.link.data(links);

    ///console.log("G.LINK (middle): \n" + JSON.stringify(g.link));

    //Get rid of old links:
    g.link.exit().remove();


    //Build new links by adding new svg lines:
    g.link
        .enter()
        .insert("line", ".node")
        .attr("class", "link");

    // create a subselection, wiring up data, using a function to define
    //how it's suppossed to know what is appended/updated/exited
    g.node = g.node.data(nodes, function (d) {
        return d.id;
    });
    //Get rid of old nodes:
    g.node.exit().remove();
    //-------------------
    //create new nodes by making groupd elements, that contain circls and text:
    var nodeEnter = g.node.enter()
        .append("g")
        .attr("class", "node")
        .on("click", click)
        .call(g.force.drag);
    //circle within the single node group:
    nodeEnter.append("circle")
        .attr("r", 4.5);

    //text within the single node group:
    nodeEnter.append("text")
        .attr("dy", "-.2em")
        .attr("dx", function (d) {
            return (d.children.length > 0) ? "-1em" : "1em";
        })
        .attr("text-anchor", function (d) {
            return (d.children.length > 0) ? "end" : "start";
        })
        .text(function (d) {
            return d.Genesets.length <= 3 ? d.Genesets : d.Genesets.length + " sets..." ;
        });
    nodeEnter.append("text")
        .attr("dy", "1em")
        .attr("dx", function (d) {
            return (d.children.length > 0) ? "-1em" : "1em";
        })
        .attr("text-anchor", function (d) {
            return (d.children.length > 0) ? "end" : "start";
        })
        .text(function (d) {
            return d.Genes.length <= 3 ? d.Genes : d.Genes.length + " genes..." ;
        });
    //All nodes, do the following:
    g.node.select("circle")
        .style("fill", color) //calls delegate
        .style("stroke", outerRingColor);
    //-------------------

    //g.node.fontcolor(textColor)
    g.node.select("text").attr("fill", textColor);

}


// Invoked from 'update'.
// The original source data is not the usual nodes + edge list,
// but rather an adjacency list of nodes and their children.
// We need a list of nodes + links for the force layout engine.
// So returns a list of all nodes under the root.
function flatten(data) {
    var nodes = [];
    for (var i = 0, len = data.length; i < len; i++) {
        data[i].orphan = true;
    }
    console.log(data.length + "HERE");
    for (var i = 0, len = data.length; i < len; i++) {
        console.log("I = " + i);
        console.log("len = " + len);
        if (data[i]._children) {
            for(var j = 0, jlen = data[i]._children.length; j < jlen; j++){
                console.log(data[i]._children[j] + " IS NOT AN ORPHAN ALSO " + i + " " + j);
                getNodeByID(data, data[i]._children[j]).orphan = false;
            }
        }
        else {
             for(var j = 0, jlen = data[i].children.length; j < jlen; j++){
                console.log(data[i].children[j] + " IS NOT AN ORPHAN ALSO " + i + " " + j);
                 getNodeByID(data, data[i].children[j]).orphan = false;
             }
        }
    }
    function recurse(node) {
        if (!getNodeByID(nodes, node.id)) {
            nodes.push(node);
        }
        else {
        }
        if (node.children.length > 0) {
            for (var i = 0, count = node.children.length; i < count; i++) {
                var nextNode = getNodeByID(data, node.children[i]);
                recurse(nextNode);
            }
        }
    }

    for (var i = 0, len = data.length; i < len; i++) {
        if (data[i].orphan) {
            recurse(data[i]);
        }
    }


    return nodes;
}


function getNodeByID(nodes, wanted_id) {
    for (var i = 0; i < nodes.length; i++) {
        if (nodes[i].id == wanted_id) {
            return nodes[i];
        }
    }
}


function getLinks(nodes) {

    var links = [];
    for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        for (var j = 0; j < n.children.length; j++) {
            var link = {
                source: n,
                target: getNodeByID(nodes, n.children[j])
            };
            links.push(link);
        }
    }

    return links;
}


//Invoked from 'update'
//Return the color of the node
//based on the children value of the
//source data item: {Genesets=..., children: {...}}
function color(d) {
    return d._children ? "#3182bd" // collapsed package
        :
        d.children.length > 0 ? "#c6dbef" // expanded package
            :
            "#ffffff"; // leaf node
}


function outerRingColor(d) {
    if (d.emphasis) {
        return "#33AD33";
    }
    else return "default";
}

function textColor(d) {
    if (d.emphasis) {
        return '#CC0000';
    }
    else return 'default';
}


function click(d) {
    if (d3.event.defaultPrevented) return; // ignore drag
    if (d.children.length > 0) {
        //console.log("collapsing node " + d.Genesets + " (" + d.id + ")");
        d._children = d.children;
        d.children = [];
        //console.log("children: " + d.children);
        //console.log("_children:" + d._children);
    } else if (d._children) {
        //console.log("expanding node " + d.Genesets + " (" + d.id + ")");
        d.children = d._children;
        d._children = null;
        //console.log("children: " + d.children);
        //console.log("_children:" + d._children);
    }
    nodes = flatten(g.data.nodes);
    var nextdepths = [0];
    for (i = 0; i < nodes.length; i++) {
        while (nodes[i].depth > nextdepths.length - 1) {
            nextdepths.push(0);
        }
        //if(nodes[i].depth == 0){
        //    nodes[i].fixed = true;
        //}
        nodes[i].py = nextdepths[nodes[i].depth] * 20 + 100;
        nodes[i].y = nextdepths[nodes[i].depth] * 20 + 100;
        nextdepths[nodes[i].depth]++;
    }
    //
    update();
}


//basically a way to get the path to an object
function searchTree(obj, search, path) {
    if (obj.Genesets === search) { //if search is found return, add the object to the path and return it
        path.push(obj);
        return path;
    }
    else if (obj.children || obj._children) { //if children are collapsed d3 object will have them instantiated as _children
        var children = (obj.children) ? obj.children : obj._children;
        for (var i = 0; i < children.length; i++) {
            path.push(obj);// we assume this path is the right one
            var found = searchTree(children[i], search, path);
            if (found) {// we were right, this should return the bubbled-up path from the first if statement
                return found;
            }
            else {//we were wrong, remove this parent from the path and continue iterating
                path.pop();
            }
        }
    }
    else {//not the right object, return false so it will continue to iterate in the loop
        return false;
    }
}

function extract_select2_data(node, leaves, index) {
    if (node.children) {
        for (var i = 0; i < node.children.length; i++) {
            index = extract_select2_data(node.children[i], leaves, index)[0];
        }
    }
    else {
        leaves.push({id: ++index, text: node.Genesets});
    }
    return [index, leaves];
}

function openPaths(paths) {
    for (var i = 0; i < paths.length; i++) {
        if (paths[i].id !== "1") {//i.e. not root
            paths[i].class = 'found';
            if (paths[i]._children) { //if children are hidden: open them, otherwise: don't do anything
                paths[i].children = paths[i]._children;
                paths[i]._children = null;
            }
            update(paths[i]);
        }
    }
}

$("#search").on("select2-selecting", function (e) {
    var paths = searchTree(root, e.object.text, []);
    if (typeof(paths) !== "undefined") {
        openPaths(paths);
    }
    else {
        alert(e.object.text + " not found!");
    }
})


//event handler for every time the force layout engine
//says to redraw everything:
function tick() {

    g.node.attr("transform", function (d) {
        d.x = d.depth * 200 + 100;
        return ("translate(" + d.x + "," + d.y + ")");
    });
    //redraw position of every link within the link set:

    g.link.attr("x1", function (d) {
        return d.source.x;
    })
        .attr("y1", function (d) {
            return d.source.y;
        })
        .attr("x2", function (d) {
            return d.target.x;
        })
        .attr("y2", function (d) {
            return d.target.y;
        });
}


var data = {
    "nodes": [
        {"id": 0, "Genesets": [1, 2, 3, 4, 5], "Genes": ["I"], "children": [1, 2], "depth": 0},
        {"id": 1, "Genesets": [1, 2, 4, 5], "Genes": ["A", "I"], "children": [3, 16], "depth": 1},
        {"id": 2, "Genesets": [2, 3, 4, 5], "Genes": ["I", "K"], "children": [6, 16], "depth": 1},
        {"id": 3, "Genesets": [1, 2, 4], "Genes": ["A", "E", "I"], "children": [7,8], "depth": 2},
        {"id": 4, "Genesets": [1, 2, 3], "Genes": ["G","I"], "children": [9,10], "depth": 2},
        {"id": 5, "Genesets": [1, 3, 4], "Genes": ["I","J"], "children": [7, 11], "depth": 2},
        {"id": 6, "Genesets": [2, 3, 4], "Genes": ["I", "K", "M"], "children": [9, 11], "depth": 2, "emphasis": true},
        {"id": 7, "Genesets": [1, 4], "Genes": ["A", "E", "I", "B", "D", "J"], "children": [12, 15], "depth": 3},
        {"id": 8, "Genesets": [1, 2], "Genes": ["A", "C", "E", "G", "I"], "children": [12, 13], "depth": 3},
        {"id": 9, "Genesets": [2, 3], "Genes": ["G", "I", "M", "P"], "children": [13, 14], "depth": 3, "emphasis": true},
        {"id": 10, "Genesets": [1, 3], "Genes": ["G", "H", "I", "J"], "children": [12, 14], "depth": 3},
        {"id": 11, "Genesets": [3, 4], "Genes": ["I", "J", "K", "L", "M", "N"], "children": [14, 15], "depth": 3, "emphasis": true},
        {"id": 12, "Genesets": [1], "Genes": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"], "children": [], "depth": 4},
        {"id": 13, "Genesets": [2], "Genes": ["A", "C", "E", "G", "I", "K", "M", "P"], "children": [], "depth": 4, "emphasis": true},
        {"id": 14, "Genesets": [3], "Genes": ["G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T"], "children": [], "depth": 4, "emphasis": true},
        {"id": 15, "Genesets": [4], "Genes": ["A", "B", "D", "E", "I", "J", "K", "L", "M", "N"], "children": [], "depth": 4, "emphasis": true},
        {"id": 16, "Genesets": [5], "Genes": ["A", "I", "K"], "children": [], "depth": 4}



        /*
        {"id": 16, "Genesets": "EXTRA1", "children": [1, 4, 7], "depth": 0},              //1
        {"id": 17, "Genesets": "EXTRA2", "children": [1, 2, 15], "depth": 0},              //1
        {"id": 18, "Genesets": "EXTRA3", "children": [2, 15, 14], "depth": 0},              //1
        {"id": 19, "Genesets": "EXTRA4", "children": [7, 13, 22], "depth": 1},              //1
        {"id": 20, "Genesets": "EXTRA5", "children": [22, 23], "depth": 1},              //1
        {"id": 21, "Genesets": "EXTRA6", "children": [12], "depth": 1},              //1
        {"id": 22, "Genesets": "EXTRA7", "children": [3, 4, 5, 12, 14, 15], "depth": 2},              //1
        {"id": 23, "Genesets": "EXTRA8", "children": [14], "depth": 2},              //1

        {"id": 0, "Genesets": "flare", "children": [1, 22], "depth": 0, "emphasis": true},                  //0
        {"id": 1, "Genesets": "analytics", "children": [2, 7, 13], "depth": 1},              //1
        {"id": 2, "Genesets": "cluster", "children": [3, 4, 5, 6, 15], "depth": 2},                //2
        {"id": 3, "Genesets": "AgglomerativeCluster", "children": [], "depth": 3},   //3
        {"id": 4, "Genesets": "CommunityStructure", "children": [], "depth": 3},     //4
        {"id": 5, "Genesets": "HierarchicalCluster", "children": [], "depth": 3},    //5
        {"id": 6, "Genesets": "MergeEdge", "children": [], "depth": 3},              //6
        {"id": 7, "Genesets": "graph", "children": [8, 9, 10, 11, 12, 15], "depth": 2},                  //7
        {"id": 8, "Genesets": "BetweennessCentrality", "children": [], "depth": 3},  //8
        {"id": 9, "Genesets": "LinkDIstance", "children": [], "depth": 3},           //9
        {"id": 10, "Genesets": "MaxFlowMinCut", "children": [], "depth": 3},          //10
        {"id": 11, "Genesets": "ShortestPaths", "children": [], "depth": 3},          //11
        {"id": 12, "Genesets": "SpanningTree", "children": [], "depth": 3},           //12
        {"id": 13, "Genesets": "optimization", "children": [14, 15], "depth": 2},           //13
        {"id": 14, "Genesets": "AspectRatioBanker", "children": [], "depth": 3},       //14
        {"id": 15, "Genesets": "TestLeaf", "children": [], "depth": 3, "emphasis": true}       //14
        */
    ]
};