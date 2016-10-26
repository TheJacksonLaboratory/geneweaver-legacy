/**
 * Visualize the output of DBSCAN
 *
 * */

// Define colors for different species
// When zooming in, color becomes solid

var speciesToColorZoomout ={"Mus musculus":"rgba(17,91,127,0.5)","Homo sapiens":"rgba(160,168,228,0.5)","Rattus norvegicus":"rgba(79,91,182,0.5)","Danio rerio":"rgba(29,42,138,0.5)","Drosophila melanogaster":"rgba(151,230,186,0.5)","Macaca mulatta":"rgba(65,188,118,0.5)","Caenorhabditis elegans":"rgba(13,143,70,0.5)","Saccharomyces cerevisiae":"rgba(255,215,168,0.5)","Gallus gallus":"rgba(255,178,88,0.5)","Canis familiaris":"rgba(201,116,18,0.5)"};
var speciesToColorZoomin = {"Mus musculus":"rgb(17,91,127)","Homo sapiens":"rgb(160,168,228)","Rattus norvegicus":"rgb(79,91,182)","Danio rerio":"rgb(29,42,138)","Drosophila melanogaster":"rgb(151,230,186)","Macaca mulatta":"rgb(65,188,118)","Caenorhabditis elegans":"rgb(13,143,70)","Saccharomyces cerevisiae":"rgb(255,215,168)","Gallus gallus":"rgb(255,178,88)","Canis familiaris":"rgb(201,116,18)"};

// Define properties for svg
var svg = d3.select("svg"),
    margin = 20,
    diameter = +svg.attr("width"),
    g = svg.append("g").attr("transform", "translate(" + diameter / 2 + "," + diameter / 2 + ")");

//define domain and colors for legend
var ordinal = d3.scaleOrdinal()
  .domain(Object.keys(speciesToColorZoomin))
  .range(Object.keys(speciesToColorZoomin).map(function(e){return speciesToColorZoomin[e]}));

var pack = d3.pack()
    .size([diameter - margin, diameter - margin])
    .padding(2);

//Parse the cluster to a format which d3 code can accept
//Basiclly root - cluster layer - gene layer(leaf)
function parse(cluster, geneToSpecies) {
    var clusters = {};
    clusters.name = "Clusters";
    clusters.children = cluster.map(function(e, i){
        var obj = {};
        obj.name = "Cluster" + i;
        obj.children = e.map(function(gene){
            console.log(geneToSpecies[gene]);
            var geneObj = {};
            geneObj.name = gene;
            geneObj.size = 1;
            geneObj.colorZoomin = speciesToColorZoomin[geneToSpecies[gene]];
            geneObj.colorZoomout = speciesToColorZoomout[geneToSpecies[gene]];
            return geneObj
        });
        return obj;
    });
    return clusters;
}

//Main function to draw svg
function draw(root) {
  //get the root
  root = d3.hierarchy(root)
      .sum(function(d) { return d.size; })
      .sort(function(a, b) { return b.value - a.value; });

  //set focus, will be used for zooming function
  var focus = root,
      nodes = pack(root).descendants(),
      view;

  var circle = g.selectAll("circle")
    .data(nodes)
    .enter().append("circle")
      .attr("class", function(d) { return d.parent ? d.children ? "node" : "node node--leaf" : "node node--root"; })
      .style("fill", function(d) {
          //set color for the largest circle(root)
          if(!d.parent)
              return "#96C7DF";
          //if d has children, then d is cluster layer, else d is in gene layer.
          //at gene layer, when the focus is root, it is at zoom out mode, otherwise zoom in mode
          return d.children ? "#64A5C4" : focus === root ? d.data.colorZoomout : d.data.colorZoomin; })
      //set onClick function to the circle, which is the zoom function
      .on("click", function(d) {
          if (focus !== d)
              if(!d.children)
                  zoom(d.parent), d3.event.stopPropagation();
              else {
                  zoom(d), d3.event.stopPropagation();
              }

      });
  //change the text when zooming between cluster and gene's name
  var text = g.selectAll("text")
    .data(nodes)
    .enter().append("text")
      .attr("class", "label")
      .style("fill-opacity", function(d) { return d.parent === root ? 1 : 0; })
      .style("display", function(d) { return d.parent === root ? "inline" : "none"; })
      .on("click", function(d) {
          //make the gene clickable--url will redirect to a search gene page
          if(!d.children) {
              var url = "/search/?searchbar=" + d.data.name + "&pagination_page=1&searchGenes=yes";
              location.href = url;
              d3.event.stopPropagation();  }})
      .text(function(d) {
          return d.data.name; });

  var node = g.selectAll("circle,text");

    svg
      .style("background", "white")
      .on("click", function() { zoom(root); });

    //set legend
    svg.append("g")
      .attr("class", "legendOrdinal")
      .attr("transform", "translate(20,20)");

    var legendOrdinal = d3.legendColor()
      .shape("path", d3.symbol().type(d3.symbolCircle).size(500)())
      .shapePadding(10)
      .scale(ordinal);

    svg.select(".legendOrdinal")
      .call(legendOrdinal);

  //zoom function
  zoomTo([root.x, root.y, root.r * 2 + margin]);

  function zoom(d) {
    var focus0 = focus; focus = d;

    var transition = d3.transition()
        .duration(d3.event.altKey ? 7500 : 750)
        .tween("zoom", function(d) {
          var i = d3.interpolateZoom(view, [focus.x, focus.y, focus.r * 2 + margin]);
          return function(t) { zoomTo(i(t)); };
        });
    transition.selectAll("circle")
      .filter(function(d) { return !d.children; })
        .style("fill", function(d) { return d.parent === focus ? d.data.colorZoomin : d.data.colorZoomout; });

    transition.selectAll("text")
      .filter(function(d) { return d.parent === focus || this.style.display === "inline"; })
        .style("fill-opacity", function(d) { return d.parent === focus ? 1 : 0; })
        .on("start", function(d) { if (d.parent === focus) this.style.display = "inline"; })
        .on("end", function(d) { if (d.parent !== focus) this.style.display = "none"; });
  }

  function zoomTo(v) {
    var k = diameter / v[2]; view = v;
    node.attr("transform", function(d) { return "translate(" + (d.x - v[0]) * k + "," + (d.y - v[1]) * k + ")"; });
    circle.attr("r", function(d) { return d.r * k; });
  }
};

