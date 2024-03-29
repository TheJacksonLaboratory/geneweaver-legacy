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


//initialization
$(function () {

    //use a global var for the data:
    g.data = data;

    //console.log("DATA = " + JSON.stringify(data));
    var width = 1200,
        height = 1000;

    var r = 6,
        fill = d3.scale.category20();



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
        //linkDistance proportional to difference in depths to prevent crowding
        .linkDistance(function (link) {
            return ((link.target.depth - link.source.depth) * 40);
        })
        //linkStrength also proportional to distance
        .linkStrength(function (link) {
            return 1 / ((link.target.depth - link.source.depth) * 1.5);
        })
        //Deeper nodes have a stronger charge because there's more jostling for space down there
        .charge(function (d) {
            return (-((d.depth+1) * 400));
        })
        .chargeDistance(300)
        .gravity(0.05)
        .size([width, height])
        .on("tick", tick);


    //Initialize positions of tree elements to reduce tangling caused by random initialization
    var nodes = flatten(g.data.nodes);
    initialize_layout(nodes);


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
    for(var i = 0; i < nodes.length; i++){
        console.log("Node " + nodes[i].id + "\n\tAbove: " + nodes[i].above + 
                    "\n\tBelow: " + nodes[i].below);
    }
    //console.log(nodes.length + " nodes to draw");


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
    g.link = g.link.data(links);


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
    	.attr("above", function(d) {
            return(d.above);
        })
    	.attr("below", function(d) {
            return(d.below);
        })
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
            //return d.Genesets.length <= 3 ? d.Genesets : d.Genesets.length + " sets..." ;
            return d.Genesets;
        });

    //
    nodeEnter.append("text")
        .attr("dy", "1em")
        .attr("dx", function (d) {
            return (d.children.length > 0) ? "-1em" : "1em";
        })
        .attr("text-anchor", function (d) {
            return (d.children.length > 0) ? "end" : "start";
        })
        .text(function (d) {
            //return d.Genes.length <= 3 ? d.Genes : d.Genes.length + " genes..." ;
            return d.Genes;
        });
    //All nodes, do the following:
    g.node.select("circle")
        .style("fill", color) //calls delegate
        .style("stroke", outerRingColor);
    //-------------------

    //g.node.fontcolor(textColor)
    g.node.select("text").attr("fill", textColor);
    
    console.log(g.force.nodes());

}


// Invoked from 'update'.
// The original source data is not the usual nodes + edge list,
// but rather an adjacency list of nodes and their children.
// We need a list of nodes + links for the force layout engine.
// So returns a list of all nodes under the root.
function flatten(data) {
    var nodes = [];
    //checks to see which nodes have no parents. these are the only nodes we will recurse on,
    //to make sure we cover the entire tree with minimum redundancy. Worth a O(n) operation once
    //to save up to n extra recursive calls, and prevents collapsed children from showing up when they
    //shouldn't
    for (var i = 0, len = data.length; i < len; i++) {
        data[i].orphan = true;
    }
    for (var i = 0, len = data.length; i < len; i++) {
        if (data[i]._children) {
            for(var j = 0, jlen = data[i]._children.length; j < jlen; j++){
                                console.log("PARAM 1: " + data + "\n PARAM 2: " + data[i]._children[j]);

                getNodeByID(data, data[i]._children[j]).orphan = false;
            }
        }
        else {
             for(var j = 0, jlen = data[i].children.length; j < jlen; j++){
                 getNodeByID(data, data[i].children[j]).orphan = false;
             }
        }
    }

    //recursively get each node's children and it's children's children. does not
    //look at collapsed children or their children.
    function recurse(node) {
        if (!getNodeByID(nodes, node.id)) {
            nodes.push(node);
        }
        if (node.children.length > 0) {
            for (var i = 0, count = node.children.length; i < count; i++) {
                var nextNode = getNodeByID(data, node.children[i]);
                recurse(nextNode);
            }
        }
    }

    //recurse on orphans only
    for (var i = 0, len = data.length; i < len; i++) {
        if (data[i].orphan) {
            recurse(data[i]);
        }
    }
    return nodes;
}

//nodes are identified in the children arrays by their ID, so we need
//this function to access the nodes.
function getNodeByID(nodes, wanted_id) {
    for (var i = 0; i < nodes.length; i++) {
        if (nodes[i].id == wanted_id) {
            return nodes[i];
        }
    }
}

//gets the array of link objects for the force diagram to use
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

function initialize_layout(nodes) {
    var nextdepths = [0];
    var previous = [-1];
    for (i = 0; i < nodes.length; i++) {
        while (nodes[i].depth > nextdepths.length - 1) {
            nextdepths.push(0);
            previous.push(-1);
        }
        if(previous[nodes[i].depth] >= 0) {
            prevNode = getNodeByID(nodes, previous[nodes[i].depth]);
            prevNode.below = nodes[i].id;
            nodes[i].above = prevNode.id;
        }
        previous[nodes[i].depth] = nodes[i].id;
        nodes[i].x = nodes[i].depth * 100 + 100;
        nodes[i].y = nextdepths[nodes[i].depth] * 20 + 100;
        nextdepths[nodes[i].depth]++;
    }
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


//Collapses nodes upon click, unless they're being dragged.
//essentially switches the "active" children array with the
// "hidden" _children array.
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
    initialize_layout(nodes);
    //
    update();
}

//NOT YET IN USE--SEARCH FUNCTIONALITY
//basically a way to get the path to an object
function searchTree(obj, search, path) {
    if (search in obj.Genesets) { //if search is found return, add the object to the path and return it
        path.push(obj);
        return path;
    }
    else if (obj.children || obj._children) { //if children are collapsed d3 object will have them instantiated as _children
        var children = (obj.children.length > 0) ? obj.children : obj._children;
        for (var i = 0; i < children.length; i++) {
            path.push(obj);// we assume this path is the right one
            var found = searchTree(getNodeByID(children[i]), search, path);
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

//NOT YET IN USE--SEARCH FUNCTIONALITY
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

//NOT YET IN USE--SEARCH FUNCTIONALITY
function openPaths(paths) {
    for (var i = 0; i < paths.length; i++) {
        if (!paths[i].orphan) {//i.e. not root
            paths[i].class = 'found';
            if (paths[i]._children) { //if children are hidden: open them, otherwise: don't do anything
                paths[i].children = paths[i]._children;
                paths[i]._children = null;
            }
            update(paths[i]);
        }
    }
}

//NOT YET IN USE--SEARCH FUNCTIONALITY
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
//says to redraw everything: keeps each node in its respective column
function tick() {
    
    for (var i = 0; i < g.force.nodes().length; i++) {
        console.log("COLLIDING NODE " + g.force.nodes()[i].id);
     	//collide(g.force.nodes()[i]);
    }
    
    g.node.attr("transform", function (d) {
        //collide(d);
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

function collide(node) {
    //node.py = node.y;
    //console.log("colliding");
	var pad = 15*Math.pow(node.depth, .3),
        ny1 = node.y - pad,
        ny2 = node.y + pad;
        if(typeof node.above !== 'undefined') {
            //console.log("collision between " + node.id + " and " + node.above);
        	var above = getNodeByID(g.force.nodes(), node.above);
            //above.py = above.y;
            var dy = node.y - above.y;
            var l = Math.abs(dy);
            pad *=2
            if(l < pad) {
                l  = (l-pad) / l * .05;
                node.y -= dy *=l;
                above.y += dy;
        	}
            if(above.y > node.y) {
             	node.above = above.above;
                above.below = node.below;
                node.below = above.id;
                above.above = node.id;
            }
    	}
        if(typeof node.below !== 'undefined') {
            //console.log("PARAM 1: " + g.force.nodes() + "\n PARAM 2: " + node.below);
        	var below = getNodeByID(g.force.nodes(), node.below);
            //below.py = below.y;
            //console.log("collision between " + node.id + " and " + node.above);
            var dy = node.y - below.y;
            var l = Math.abs(dy);
            pad*=2
            if(l < pad) {
                l  = (l-pad) / l * .05;
                console.log("L = " + l);
                node.y -= dy *=l;
                below.y += dy;
        	}
            if(below.y < node.y) {
             	node.below = below.below;
                below.above = node.above;
                node.above = below.id;
                below.below = node.id;
            }
    	}
}


//sample data. we can load it from a separate file and make it work, but we're
//choosing not to for the beta demonstration, in case that causes a hiccup on a different machine.
//
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