/**
 * Created by olatunde on 10/1/16.
 */
/**
 * file:  UpSet.js
 * desc:  d3js code for visualizing upset bar charts
 * auth: Oyinda Olatunde
 */

/**
 * UpSet module. For drawing the bar chart.
 */
var upset = function () {

    var exports = {},
        // SVG object
        svg = null,
        // SVG width in pixels
        width = 1100,
        // SVG height in pixel
        height = 900,
        // Bar chart margins
        margin = {
            top: 20,
            right: 20,
            bottom: 50,
            left: 300
        },
        //Padding between each individual bar
        diagramPadding = 0.5,
        // Bar data for each bar
        Intersectionbars = [],
        // Individual bar text lines
        barText = [],
        // Y-axis/X-axis labels for the bar chart
        chartLabels = [],
        // Chart dimensions
        chartWidth = +width - margin.left - margin.right,
        chartHeight = 450,
        // Bar chart colours: un-query black-grey, and query purple
        fillColours = ['#C0C0C0', '#8E44AD'],
        // Data returned by the tool
        data = null;

    /** private **/

    /**
     * Transforms the bar chart data returned by the tool into a format
     * ready for display.
     *
     * Assumptions:
     */
    var makeBars = function () {
        for (var i = 0; i < data.bar_diagrams.length; i++) {
            var set = data.bar_diagrams[i];

            var bar = {
                fill: fillColours[0],
                height: set['intersection'],
                desc: set['desc1'],
                name: set['name1']
            };

            Intersectionbars.push(bar);
        }
    };

    /** public **/

    /**
     * Draws the bar graph
     */
    exports.draw = function () {
        makeBars();

        var x = d3.scaleBand().range([0, chartWidth]).domain(Intersectionbars.map(function(d) { return d.name; })).padding(diagramPadding),
            y = d3.scaleLinear().range([chartHeight, 0]).domain([0, d3.max(Intersectionbars, function(d) { return d.height})]);

        //Append svg to the upset area
        svg = d3.select("#upset").append("svg")
            .attr("width", width)
            .attr("height", height)
            .append("g")
            .attr("transform", "translate(" + (margin.left + margin.right) + "," + margin.top + ")");

        //Append the y axis the svg
        svg.append("g")
            .call(d3.axisLeft(y));

        //TODO this does not show the axis title
        svg.selectAll("g")
            .append("text")
            .attr("transform", "rotate(-90")
            .attr("y",chartHeight - margin.left)
            .attr("x",chartWidth - (height / 2))
            .attr("dy", "1em")
            .style("text-anchor", "middle")
            .text("Intersection Size");

        //Append Intersectionbars to the graph
        svg.selectAll("bar")
            .data(Intersectionbars)
            .enter().append("rect")
            .attr("class", "bar")
            .attr("width", x.bandwidth())
            .attr("x", function(d) { return x(d.name); })
            .attr("y", function(d) { return y(d.height); })
            .attr("height", function (d) { return chartHeight - y(d.height); })
            .style("fill", function (d) { return d.fill; })
            .on("mouseover", function(d){

                //Mouse over events generate and display a tooltip with
                //with intersection data

                d3.select("#upset")
                    .append("div")
                    .attr("id", "up-tooltip")
                    .attr("class", "tooltip")
                    .style("opacity", 0.9)
                    .html(d.name + "<br />" + d.desc)
                    .style("left", d3.event.pageX + "px")
                    .style("top", d3.event.pageY + "px");

            })
            .on("mouseout", function(d) {
                d3.select("#up-tooltip").remove();
            });

        svg.selectAll("text.bar")
            .data(Intersectionbars)
            .enter().append("text")
            .attr("class", "bar")
            .attr("text-anchor", "right")
            .attr("x", function(d) { return x(d.name);})
            .attr("y", function(d) { return y(d.height) - 10;})
            .text(function(d) {return d.height;});

        return exports;
    };

    /**
     * Setters/getters
     */
    exports.data = function (_) {
        if(!arguments.length) return data;
        data = _;
        return exports;
    };

    exports.diagramPadding = function (_) {
        if(!arguments.length) return diagramPadding;
        diagramPadding = +_;
        return exports;
    };

    exports.height = function(_) {
        if (!arguments.length) return height;
        height = +_;
        return exports;
    };

    exports.width = function(_) {
        if (!arguments.length) return width;
        width = +_;
        return exports;
    };

    exports.xShift = function(_) {
        if (!arguments.length) return xShift;
        xShift = +_;
        return exports;
    };


    exports.yShift = function(_) {
        if (!arguments.length) return yShift;
        yShift = +_;
        return exports;
    };

    return exports;
};