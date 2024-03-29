/**
 * file: selected.js
 * desc: Code to keep track of, update, and access selected projects and genesets.
 *
 * auth: Alexander Berger
 **/

/**
 * This closure provides an abstracted way to keep track of selected projects and genesets.
 * This was initially created to update the multi-select inputs for the MSET tool, but was
 * designed to be used by any number of tools that might need access to this information.
 *
 * Just think of it as a JavaScript entity that reaaalllyyy wants to be a class.
 *
 **/

var selected = function(){
    var sProj = [],
        sGs = [];

    function s2data() {
        return [
            {
                'text': 'Projects',
                'children': projects.selected
            },
            {
                'text': 'Genesets',
                'children': genesets.selected
            }
        ];
    }

    /* A very simple promise/subscription api */
    var watchers = [];

    function watch(callback){
        watchers.push(callback);
    }

    function unwatch(callback){
        var idx = watchers.indexOf(callback);
        watchers.splice(idx, 1);
    }

    function updateWatchers(){
        for (var i = watchers.length; i--;) {
            watchers[i]();
        }
    }

    function add(el){
        var el_name = el.attr('name'),
            s = el_name.split('_');
        if (s[0] == 'project') {
            console.log(el.data('project-name'));
            selected.projects.add(el_name, el.data('project-name'))
        } else if (s[0] === 'geneset') {
            selected.genesets.add(el_name, 'GS'+s[1])
        }
    }
    function remove(el){
        var el_name = el.attr('name'),
            s = el_name.split('_');
        if (s[0] == 'project') {
            selected.projects.remove(s[1])
        } else if (s[0] === 'geneset') {
            selected.genesets.remove(s[1])
        }
    }

    var projects = function(){
        var selected = sProj;
        function add(project_id, display_name){
            _safeAdd(selected, project_id, display_name)
        }
        function remove(project_id){
            _safeRemove(selected, project_id)
        }
        function s2data() {
            return selected;
        }
        return {
            add:add,
            remove:remove,
            selected: selected,
            select2: s2data
        }
    }();

    var genesets = function(){
        var selected = sGs;
        function add(gs_id, display_name){
            _safeAdd(selected, gs_id, display_name)
        }
        function remove(gs_id){
            _safeRemove(selected, gs_id)
        }
        function s2data(){
            return selected;
        }
        return {
            add:add,
            remove:remove,
            selected: selected,
            select2: s2data
        }
    }();

    function _safeAdd(arr, id, name){
        var exists = false;
        for(var i = 0; i < arr.length; i++) {
            if (arr[i].id == id) {
                exists = true;
                break;
            }
        }
        if (!exists) {
            arr.push({'id': id, 'text': name});
            updateWatchers()
        }
    }

    function _safeRemove(arr, id){
        for (var i = arr.length; i--;) {
            if (arr[i].id === id) {
                arr.splice(i, 1);
                break;
            }
        }
        updateWatchers();
    }

    return {
        add:add,
        remove:remove,
        projects:projects,
        genesets:genesets,
        select2:s2data,
        watch: watch,
        unwatch: unwatch
    }
}();
