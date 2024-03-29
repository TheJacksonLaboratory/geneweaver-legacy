/**
 * file: tags.js
 * desc: Code for dynamically generating species and attribution tags. 
 *       Requires JQuery to be loaded before this file. 
 * auth: TR
 */

/**
 * Generates attribution tags using a list of colors generated from ColorBrewer
 * scales. Each attribution tag (the HTML span) should have the class:
 * att-ATTRIBUTION-LABEL, where the ATTRIBUTION-LABEL is derived from the
 * gs_abbreviation column in the attribution table. This function generates the
 * tags and alters each attribution span element.
 *
 * arguments
 *      attribs: an object mapping attribution IDs -> to their labels
 *
 */
var makeAttributionTags = function(attribs) {
    // Two, combined color Brewer palettes
    var colors = [
        'rgb(228,26,28)', 'rgb(55,126,184)', 'rgb(77,175,74)',
        'rgb(152,78,163)', 'rgb(255,127,0)', 'rgb(255,255,51)',
        'rgb(166,86,40)', 'rgb(247,129,191)', 'rgb(153,153,153)',
        'rgb(102,194,165)', 'rgb(252,141,98)', 'rgb(141,160,203)',
        'rgb(231,138,195)', 'rgb(166,216,84)', 'rgb(255,217,47)',
        'rgb(229,196,148)', 'rgb(179,179,179)'
    ];

    if (!attribs)
        return;

    for (var key in attribs) {
        attrib = attribs[key];

        $('.att-' + attrib).attr('class', 'group_name att-' + attrib);
        $('.att-' + attrib).css('background-color', colors.shift());
        $('.att-' + attrib).css('margin', '-5px 0 0 5px');
        $('.att-' + attrib).html(attrib.toUpperCase());
    }
};

/**
 * Generates all species tags using the given list of species. Each species tag
 * element should have the class sp-tag-SPID, where SPID is the species ID
 * present in the species table. 
 *
 * Assumes the species list is in a particular order since geneweaverdb almost
 * always returns an OrderedDict.
 * 
 * arguments
 *      splist: a list of tuples, (sp_id, sp_name)
 *      fullName: if true, creates a tag using the full species name instead 
 *                of the abbreviation
 */
var makeSpeciesTags = function(splist, fullName) {

    var colors = [
        '#fae4db', '#f9fac5', '#b5faf5', '#fae3e9', '#f5fee1', '#f4dfff',
        '#78c679', '#41b6c4', '#7bccc4', '#8c96c6', '#fc8d59'
    ];
    var borders = [
        '#eeb44f', '#d7c000', '#44fcf7', '#fca5b7', '#8fcb0a', '#b4d1fb',
        '#41ab5d', '#1d91c0', '#4eb3d3', '#8c6bb1', '#ef6548'
    ];

    if (!splist)
        return;

    for (var i = 0; i < splist.length; i++) {

        var spid = splist[i][0];
        var spname = splist[i][1];

        if (!spname)
            continue;

        if (!colors)
            break;

        if (fullName === undefined || !fullName) {

            // Elissa mentioned we shouldn't use common, pleb names for species
            // (and that monkey isn't technically a species), so we properly 
            // abbreviate the species name.
            spname = spname.split(' ');

            // Probably the null species (sp_id == 0)
            if (spname.length === 1)
                continue;

            // Mus musculus and Macaca mulatta have the same abbreviation, so the
            // latter is abbreviated to M. mul instead of Mm.
            if (spname[1].slice(0, 3) == 'mul')
                spname = spname[0][0].toUpperCase() + '.' + 'mul' + '.';
            else
                spname = spname[0][0].toUpperCase() + spname[1][0].toLowerCase() + '.';
        }

        $('.sp-tag-' + spid).attr('class', 'group_name sp-tag-' + spid);
        $('.sp-tag-' + spid).css('background-color', colors.shift());
        $('.sp-tag-' + spid).css('border', '1px solid');
        $('.sp-tag-' + spid).css('border-color', borders.shift());
        $('.sp-tag-' + spid).css('margin', '-5px 0 0 5px');
        $('.sp-tag-' + spid).css('font', 'italic 10px/14px Georgia, serif');
        $('.sp-tag-' + spid).html(spname);
    }
};

/**
 * Returns a mapping of sp_ids to the associated species color. Used to color
 * the species name on the upload page so users get the idea that species have
 * a speciel coloring/tag (Elissa's suggestion).
 *
 * Assumes the species list is in a particular order since geneweaverdb almost
 * always returns an OrderedDict.
 *
 * arguments
 *      species: an object mapping sp_ids to species names
 *
 * returns
 *      an object whose keys are sp_ids and values are colors
 */
var getSpeciesColors = function(species) {

    var colors = [
        '#fae4db', '#f9fac5', '#b5faf5', '#fae3e9', '#f5fee1', '#f4dfff',
        '#78c679', '#41b6c4', '#7bccc4', '#8c96c6', '#fc8d59'
    ];
    var mapping = {};

    if (!species)
        return;

    for (var spid in species) {

        if (spid == 0) {

            mapping[spid] = '';
            continue;
        }

        if (!colors)
            break;

        mapping[spid] = colors.shift();
    }

    return mapping;
}

/**
 * Dynamically generates a set of colored ontology tags for the given set of
 * annotations. For each ontology found in the set of annotations a color coded
 * label key is made and attached to a special div (since this script is only
 * called from /viewgenesetdetails or /editgenesetgenes). Then each annotation
 * is colored according to the key and its element is modified to reflect this.
 *
 * arguments
 *      onts: list of ontology annotations for a single geneset
 */
var makeOntologyTags = function(onts) {

    var colors = [
        '#ccebc5', '#fbb4ae', '#decbe4', '#b3cde3', '#fed9a6', '#ffffcc', 
        '#e5d8bd', '#fddaec', '#f2f2f2'
    ];

    var borders = [
        '#66855F', '#954E48', '#78657E', '#4D677D', '#987340', '#999966', 
        '#7f7257', '#977486', '#8C8C8C'
    ];

    // Remove duplicate ontology IDs since we're getting a list of all
    // annotations
    onts = function(a) {
        var seen = {};
    
        return a.filter(function(elem) {
            return seen.hasOwnProperty(elem.ontdb_id) ? false : (seen[elem.ontdb_id] = true);
        });
    }(onts);

    var ontIndex = {};

    // Normalizes the ontology IDs so they begin from zero and are sequential
    // with no gaps inbetween
    for (var i = 0; i < onts.length; i++) {

        if (ontIndex.hasOwnProperty(onts[i].ontdb_id))
            continue;

        ontIndex[onts[i].ontdb_id] = Object.keys(ontIndex).length;
    }

    for (var i = 0; i < onts.length; i++) {

        var ontid = onts[i].ontdb_id;
        var index = ontIndex[onts[i].ontdb_id];
        var name = onts[i].dbname;

        $('.ont-' + ontid).css('background-color', colors[index]);
        $('.ont-' + ontid).css('border', '1px solid');
        $('.ont-' + ontid).css('border-color', borders[index]);

        var $key = $('<div>', {
            class: 'ontology-tag', 
            text: name
        });

        $key.css('background-color', colors[index]);
        $key.css('border', '1px solid');
        $key.css('border-color', borders[index]);
        $key.css('font-weight', 'bold');

        $('#ont-key').append($key);
    }
};

