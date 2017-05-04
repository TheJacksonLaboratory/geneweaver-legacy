/**
 * file: searchResultModals.js
 * desc: Code to abstract modal handling to avoid duplication
 *       Requires JQuery to be loaded before this file.
 * auth: Alexander Berger
 */


// A function to display the error modal
var showErrorModal = function(message) {
$('#showGenericModal').find('.modal-header')
    .removeClass('bg-green')
    .addClass('bg-red');
$('#showGenericModal').find('.modal-title')
	.html('Error!');
$('#showGenericModal').find('#genericMessage')
	.html(message);
$('#showGenericModal').modal('show');
}

// Submit the modal information for 'Share w Group' and 'Add t' via AJAX
var submitGSModalAjax = function(url, data) {
$.ajax({
    type: "GET",
    url: url,
    data: data,
    success: function (data) {
	var v = JSON.parse(data);
	if (v["error"] != 'None') {
	    console.log("Error returned " + v['error']);
	    $("#result").html('<div class="alert alert-danger fade in"> ' +
		'<button type="button" class="close" data-dismiss="alert" aria-hidden="true">x' +
		'</button>' + v['error'] + '</div>');
	} else {
	    console.log('no error');
	    $("#result").html('<div class="alert alert-success fade in"> ' +
		'<button type="button" class="close" data-dismiss="alert" aria-hidden="true">x' +
		'</button>Geneset(s) submitted successfully.</div>');
	}

    },
    error: function (jqXHR, textStatus, errorThrown ) {

	$(document).trigger("add-alerts", [{
	    'message': "An Error (" + jqXHR + ") occurred while submitting the geneset(s)",
	    'priority': 'danger'
	}]);
    }

});

}

// Open a geneset modal and update selected genesets label
var openGSModal = function(modalID, gschecked) {
return function() {
    genesets = Object.keys(gschecked);

    // If no genesets selected, display geneneric error modal.
    if (genesets.length === 0) {
	showErrorModal('You must first select Genesets to add.');
    } else {
	var gsString = genesets.map(function(s){ return 'GS' + s; }).join(', ');
	$(modalID).find(modalID+'-label').html(gsString);
	$(modalID).find(modalID+'Value').val(genesets.join(','));
	$(modalID).modal('show');
    }
}
}

// Collect data from modal for ajax call, or display error if needed
var submitGSModal = function(modalID, url) {
return function() {
    var selected = $(modalID+' select').val().map(Number);

    var option = JSON.stringify(selected);
    var g = $(modalID+'Value').val();
    var npn = null;

    var newNameElement = $(modalID+'NewName')

    if (newNameElement.length && newNameElement.val().length > 0) {
	npn = $(modalID+'NewName').val();
    }

    if ($.isEmptyObject(selected) && $.isEmptyObject(npn)){
	$("#result").html('<div class="alert alert-danger fade in"> ' +
		'<button type="button" class="close" data-dismiss="alert" aria-hidden="true">x' +
		'</button>No Projects Were Selected</div>');
    } else {
	var data = {"npn": npn, "gs_id": g, "option": option}
	submitGSModalAjax(url, data);
    }
}
}
