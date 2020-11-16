// https://observablehq.com/@d3/hierarchical-edge-bundling@426
export default function define(runtime, observer) {
  const main = runtime.module();
  const fileAttachments = new Map([["flare.json",new URL("./job1.json",import.meta.url)]]);
  main.builtin("FileAttachment", runtime.fileAttachments(name => fileAttachments.get(name)));
  main.variable(observer()).define(["md","colorout","colorin"], function(md,colorout,colorin){return(
md`# Hierarchical Edge Bundling

Hover a class to reveal its imports (<b style="color: ${colorout};">outgoing</b> edges) and classes that import it (<b style="color: ${colorin};">incoming</b> edges).`
)});

  main.variable(observer("chart")).define("chart", ["tree","bilink","d3","data","width","id","colornone","line","colorin","colorout"], function(tree,bilink,d3,data,width,id,colornone,line,colorin,colorout)
{
  const root = tree(bilink(d3.hierarchy(data)
      .sort((a, b) => d3.ascending(a.height, b.height) || d3.ascending(a.data.name, b.data.name))));

  const svg = d3.create("svg")
      .attr("viewBox", [-width / 2, -width / 2, width, width]);

  const node = svg.append("g")
      .attr("font-family", "sans-serif")
      .attr("font-size", 10)
    .selectAll("g")
    .data(root.leaves())
    .join("g")
      .attr("transform", d => `rotate(${d.x * 180 / Math.PI - 90}) translate(${d.y},0)`)
    .append("text")
      .attr("dy", "0.31em")
      .attr("x", d => d.x < Math.PI ? 6 : -6)
      .attr("text-anchor", d => d.x < Math.PI ? "start" : "end")
      .attr("transform", d => d.x >= Math.PI ? "rotate(180)" : null)
      .text(d => d.data.name)
      .each(function(d) { d.text = this; })
      .on("mouseover", overed)
      .on("mouseout", outed)
      .call(text => text.append("title").text(d => `${id(d)}
${d.outgoing.length} outgoing
${d.incoming.length} incoming`));

  const link = svg.append("g")
      .attr("stroke", colornone)
      .attr("fill", "none")
    .selectAll("path")
    .data(root.leaves().flatMap(leaf => leaf.outgoing))
    .join("path")
      .style("mix-blend-mode", "multiply")
      .attr("d", ([i, o]) => line(i.path(o)))
      .each(function(d) { d.path = this; });

  function overed(event, d) {
    link.style("mix-blend-mode", null);
    d3.select(this).attr("font-weight", "bold");
    d3.selectAll(d.incoming.map(d => d.path)).attr("stroke", colorin).raise();
    d3.selectAll(d.incoming.map(([d]) => d.text)).attr("fill", colorin).attr("font-weight", "bold");
    d3.selectAll(d.outgoing.map(d => d.path)).attr("stroke", colorout).raise();
    d3.selectAll(d.outgoing.map(([, d]) => d.text)).attr("fill", colorout).attr("font-weight", "bold");
  }

  function outed(event, d) {
    link.style("mix-blend-mode", "multiply");
    d3.select(this).attr("font-weight", null);
    d3.selectAll(d.incoming.map(d => d.path)).attr("stroke", null);
    d3.selectAll(d.incoming.map(([d]) => d.text)).attr("fill", null).attr("font-weight", null);
    d3.selectAll(d.outgoing.map(d => d.path)).attr("stroke", null);
    d3.selectAll(d.outgoing.map(([, d]) => d.text)).attr("fill", null).attr("font-weight", null);
  }

  return svg.node();
}
);


  main.variable(observer("data")).define("data", ["hierarchy","FileAttachment"], async function(hierarchy,FileAttachment){return(
hierarchy(await FileAttachment("flare.json").json())
)});


  main.variable(observer("hierarchy")).define("hierarchy", function(){return(
function hierarchy(data, delimiter = ".") {
  let root;
  const map = new Map;
  data.forEach(function find(data) {
    const {name} = data;
    if (map.has(name)) return map.get(name);
    const i = name.lastIndexOf(delimiter);
    map.set(name, data);
    if (i >= 0) {
      find({name: name.substring(0, i), children: []}).children.push(data);
      data.name = name.substring(i + 1);
    } else {
      root = data;
    }
    return data;
  });
  return root;
}
)});


  main.variable(observer("bilink")).define("bilink", ["id"], function(id){return(
function bilink(root) {
  const map = new Map(root.leaves().map(d => [id(d), d]));
  for (const d of root.leaves()) d.incoming = [], d.outgoing = d.data.imports.map(i => [d, map.get(i)]);
  for (const d of root.leaves()) for (const o of d.outgoing) o[1].incoming.push(o);
  return root;
}
)});

  main.variable(observer("id")).define("id", function(){return(
function id(node) {
  return `${node.parent ? id(node.parent) + "." : ""}${node.data.name}`;
}
)});
  main.variable(observer("colorin")).define("colorin", function(){return(
"#00f"
)});
  main.variable(observer("colorout")).define("colorout", function(){return(
"#f00"
)});
  main.variable(observer("colornone")).define("colornone", function(){return(
"#ccc"
)});
  main.variable(observer("width")).define("width", function(){return(
954
)});
  main.variable(observer("radius")).define("radius", ["width"], function(width){return(
width / 2
)});
  main.variable(observer("line")).define("line", ["d3"], function(d3){return(
d3.lineRadial()
    .curve(d3.curveBundle.beta(0.85))
    .radius(d => d.y)
    .angle(d => d.x)
)});
  main.variable(observer("tree")).define("tree", ["d3","radius"], function(d3,radius){return(
d3.cluster()
    .size([2 * Math.PI, radius - 100])
)});
  main.variable(observer("d3")).define("d3", ["require"], function(require){return(
require("d3@6")
)});
  return main;
}
