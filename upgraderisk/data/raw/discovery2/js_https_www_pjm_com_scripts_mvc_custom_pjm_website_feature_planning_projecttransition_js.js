
/************* Startup code ********/
jQuery(document).ready(function ($) {

    let ctl = document.getElementById("hidProjectTransition_isPostBack");
    if (ctl != null) {
        if (ctl.value != "true") {
            ctl.value = true;

            ctl = document.getElementById("projTransitionExtFilters");
            removeSessionMemory();
            InitExtFilters(ctl.id);
            let gridId = ctl.getAttribute("grid-id");
            InitFilters(gridId);
            SetInitSort(gridId);
            InitializeFiltersDetectEmpty();

            ctl = document.getElementById("NucraGridFilters");
            InitExtFilters(ctl.id);
            jQuery("#NucraGridFilters").css("display", "none");
            ApplyProjectTypeDisabledFilters("projTransitionExtFilters");
        }
    }

    var selectBox3 = jQuery("#ProjectTransition_ProjectTypesTabs")[0];
    selectBox3.addEventListener("focus", function (e) {
        setMemoryState();
    });

});

function removeSessionMemory() {
    var keysSessionMemory = Object.keys(sessionStorage);

    for (var sessionState of keysSessionMemory) {
        // skip loop if the property is from prototype
        if (sessionState.startsWith("SISReport") || sessionState.startsWith("ClusterReport") || sessionState.startsWith("NUCRA")) {
            sessionStorage.removeItem(sessionState);
        }
    }

}

async function mergeSessionMemory(nextTuple) {
    var keysSessionMemory = Object.keys(sessionStorage);

    var models = []
    for (var sessionState of keysSessionMemory) {
        // skip loop if the property is from prototype
        if (sessionState.startsWith("SISReport")) {
            var modelStr = sessionStorage.getItem(sessionState);
            var decodedString = decodeURIComponent(modelStr);
            var model = JSON.parse(decodedString);
            models.push(model);
        }
    }

    var sendingModel = new Object();
    sendingModel["AllModels"] = models;
    sendingModel["CurrentTuple"] = getMemoryStateTuple();
    sendingModel["NextTuple"] = nextTuple;

    var sendingModelStr = JSON.stringify(sendingModel);

    var result = await jQuery.post("/m/ProjectTransition/mergeSISReport", { jsonModel: sendingModelStr }, function (result) {
        return result;
    });

    return result;
}

function resetProjectTransition() {
    removeSessionMemory();
    location.reload();
}

function SendBodyRequest(model, gridId) {

    let modelStr = JSON.stringify(model);
    //alert(modelStr);

    //reload the body of the table    
    let url = getTableBodyUrl(gridId); // + "?jsonModel=" + modelStr;
    let bodyId = getTableBodyId(gridId);
    jQuery.post(url, { jsonModel: modelStr }, function (result) {
        jQuery("#" + bodyId).html(result);
    });
}

function IsProjConstPostBack() {
    let ctl = document.getElementById("hidCostAlloc_isPostBack");
    if (ctl != null) {
        return ctl.value == "true";
    }
}

function ResetProjConstExtFilters(containerId) {
    if (containerId == null)
        return;
    let container = document.getElementById(containerId)

    //reset the external filters    
    let extFilters = jQuery("#" + containerId).find("[data-type='filter-ext']");
    if (extFilters != null) {
        let fLen = extFilters.length;
        for (let i = 0; i < fLen; i++) {
            //let filter = new vanillaSelectBox("#"+extFilters[i].id);
            //remove the event if was added before
            //jQuery("#" + filter.id).off("change");
            ClearFilter(extFilters[i]);
            //extFilters[i].empty();
        }
    }

}

function InitializeFiltersDetectEmpty() {
    var allFilters = jQuery(".ext-filter");

    if (allFilters != null) {
        let fLen = allFilters.length;
        for (let i = 0; i < fLen; i++) {
            //let filter = new vanillaSelectBox("#"+extFilters[i].id);
            //remove the event if was added before
            //jQuery("#" + filter.id).off("change");
            DeactivateOnEmpty(allFilters[i]);
            //extFilters[i].empty();
        }
    }
}

function DeactivateOnEmpty(obj) {

    if (jQuery(obj).attr("data-enabled-on-empty") == "false") {
        var currentButton = jQuery(jQuery(obj).find("button"));

        var currentFilterTab = jQuery("#ProjectTransition_ProjectTypesTabs").val();
        if (currentButton != null && currentButton.length > 0) {
            if (currentFilterTab == 'Select Project Type') {
                var text = jQuery(jQuery(obj).find(".ext-filter-name"));
                currentButton[0].classList.add("disabled");
                currentButton.prop("disabled", "true")
                jQuery(text).css("color", "grey");
                var resetButton = jQuery("#projTransitionExtFilters > input.button.button-wide-filter.reset");
                resetButton.prop("disabled", "true")
                jQuery("#transition-projects_exportExcelFiltered").hide();
                jQuery("#transition-projects_exportXMLFiltered").hide();
                jQuery("#transition-projects_filtered_text").hide();



            }
            //else if (currentFilterTab == 'Cluster Report'){
            //    var text = jQuery(jQuery(obj).find(".ext-filter-name"));
            //    currentButton[0].classList.remove("disabled");
            //    jQuery(text).css("color", "black");
            //    var resetButton = jQuery("#projTransitionExtFilters > input.button.button-wide-filter.reset");
            //    currentButton.removeAttr("disabled");
            //    resetButton.removeAttr("disabled");
            //    jQuery("#transition-projects_exportExcelFiltered").show();
            //    jQuery("#transition-projects_exportXMLFiltered").show();
            //    jQuery("#transition-projects_filtered_text").show()

            //}
            else { //NUCRA & Cluster Report
                var text = jQuery(jQuery(obj).find(".ext-filter-name"));
                currentButton[0].classList.remove("disabled");
                jQuery(text).css("color", "black");
                var resetButton = jQuery("#projTransitionExtFilters > input.button.button-wide-filter.reset");
                currentButton.removeAttr("disabled");
                resetButton.removeAttr("disabled");
                jQuery("#transition-projects_exportExcelFiltered").show();
                jQuery("#transition-projects_exportXMLFiltered").show();
                jQuery("#transition-projects_filtered_text").show()

            }
        }
    }
}

function ResetProjTransitionPostBackFlag() {
    let ctl = document.getElementById("hidProjectTransition_isPostBack");
    if (ctl != null) {
        ctl.value = false;
    }
}

function ResetProjConst() {
    location.reload();
}

//function ResetProjConst() {
//    ResetProjConstPostBackFlag();
//    let gridId = document.getElementById("projConstExtFilters").getAttribute("grid-id");
//    ResetProjConstExtFilters("projConstExtFilters");
//    ResetProjConstFilters(gridId);
//    ResetGrid(gridId); 
//    return false;
//}

function ResetProjConstFilters(gridId) {
    if (gridId == null)
        return;

    let filters = jQuery("#" + gridId).find("[data-type='filter']");
    if (filters != null) {
        let fLen = filters.length;
        for (let i = 0; i < fLen; i++) {
            //let filter = new vanillaSelectBox("#"+filters[i].id);
            //remove the event if was added before
            //jQuery("#" + filters[i].id).off("change");            
            ClearFilter(filters[i]);
            //filters[i].empty();
        }
    }
}


//InitFilters(gridId);




function SwitchDescTab(obj) {
    var data_grid_id = "ProjectTransition";
    ResetTabs()
    SwitchTab(data_grid_id, "Desc");
    obj.setAttribute("class", "active")
}

function SwitchPATab(obj) {

    var data_grid_id = "ProjectTransition";
    ResetTabs()
    SwitchTab(data_grid_id, "PA");
    obj.setAttribute("class", "active")
}

function ResetTabs() {
    var tabs = jQuery(".ui-tabs-nav")[0].children

    for (var tab of tabs) {
        tab.setAttribute("class", "")
    }
}


function processMergeSession(result) {


    var gridId = "ProjectTransition";


    //if provided object is a paginator, use its value, otherwise pick any paginator
    let paginator = null;

    paginator = getAPaginatorObj("ProjectTransition");




    let filters = jQuery("#ProjectTransition").find("[data-type='filter']");

    extFiltersContainter = "projTransitionExtFilters";

    let allFilters = filters;
    if (extFiltersContainter != null) {
        let extFilters = jQuery("#" + extFiltersContainter).find("[data-type='filter-ext']");
        if (extFilters != null) {
            let fLen = extFilters.length;
            for (let i = 0; i < fLen; i++) {
                allFilters.push(extFilters[i]);
            }
        }
    }

    //add Nucra ext filters
    extFiltersContainter = "NucraGridFilters";

    if (extFiltersContainter != null) {
        let extFilters = jQuery("#" + extFiltersContainter).find("[data-type='filter-ext']");
        if (extFilters != null) {
            let fLen = extFilters.length;
            for (let i = 0; i < fLen; i++) {
                allFilters.push(extFilters[i]);
            }
        }
    }

    var model = BuildRefreshRequestModel(
        gridId, filters,
        paginator);


    if (result == null) {
        SendRequestProjectTransition(model, gridId, function () {
            ReinitGrid(gridId);
            var sortOrder = GetSorting()[2];

            if (sortOrder != null) {
                SetSortNoRefresh(GetSorting()[2]);
            }
            else {
                jQuery("#" + gridId).find("[img-sort-type='asc']").addClass("grid-hidden");
                jQuery("#" + gridId).find("[img-sort-type='desc']").addClass("grid-hidden");
            }
            ActivateCorrectTab();
        });
    }

    else {
        SendRequestProjectTransitionWithSearchModel(model, result, gridId, function () {
            ReinitGrid(gridId);
            var sortOrder = GetSorting()[2];

            if (sortOrder != null) {
                SetSortNoRefresh(GetSorting()[2]);
            }
            else {
                jQuery("#" + gridId).find("[img-sort-type='asc']").addClass("grid-hidden");
                jQuery("#" + gridId).find("[img-sort-type='desc']").addClass("grid-hidden");
            }
            ActivateCorrectTab();
        });
    }




}

async function SwitchTab(gridId, tab) {
    //console.log("gridId="+ gridId);
    //let filters = $("#"+gridId).find(".filter");

    SetPartialRefreshFlag(gridId, false);

    jQuery("#ProjectTransition_HiddenTab").val(tab);

    processMergeSession();

    /*await mergeSessionMemory(nextTuple).then((result) => {
        
    });*/



    ResetProjTransitionPostBackFlag();
}




function RefreshGridWithExtFiltersProjTrans(obj, extFiltersContainter, bodyOnly = true, resetCurrPage = true) {
    if (obj == null)
        return;

    //jQuery('#loader').fadeOut('fast');
    let gridId = obj.getAttribute("data-grid-id");
    if (resetCurrPage == true) {
        SetPaginatorsAttribute(gridId, "data-current-page", 1);
    }

    ApplyProjectTypeDisabledFilters(extFiltersContainter);
    let filters = jQuery("#" + gridId).find("[data-type='filter']");


    let allFilters = filters;
    if (extFiltersContainter != null) {
        let extFilters = jQuery("#" + extFiltersContainter).find("[data-type='filter-ext']");
        if (extFilters != null) {
            let fLen = extFilters.length;
            for (let i = 0; i < fLen; i++) {
                allFilters.push(extFilters[i]);
            }
        }
    }
    let paginator = getAPaginatorObj(gridId);

    var model = BuildRefreshRequestModel(
        gridId, filters,
        paginator);


    removeSessionMemory();

    //SendBodyRequest(BuildRefreshRequestModel(gridId, allFilters, paginator), gridId);

    if (bodyOnly) {
        SetPartialRefreshFlag(gridId, true);
        SendBodyRequest(model, gridId);
    }
    else {
        SetPartialRefreshFlag(gridId, false);

        SendRequestProjectTransition(model, gridId, function () {
            ReinitGrid(gridId);

            var sortOrder = GetSorting()[2];
            if (sortOrder != null) {
                SetSortNoRefresh(GetSorting()[2]);
            }
            else {
                jQuery("#" + gridId).find("[img-sort-type='asc']").addClass("grid-hidden");
                jQuery("#" + gridId).find("[img-sort-type='desc']").addClass("grid-hidden");
            }
            InitializeFiltersDetectEmpty();

            ApplyProjectTypeDisabledFilters(extFiltersContainter);
        });
    }
}

function ApplyProjectTypeDisabledFilters(containerId) {
    if (!containerId)
        return;

    const $container = jQuery("#" + containerId);
    const extFilters = $container.find("[data-disabled-on-project-types]");

    if (!extFilters.length)
        return;

    const selectedProjectType = GetSelectedProjectTypeValue();
    let shouldReinit = false;

    extFilters.each(function () {
        shouldReinit = ToggleProjectTypeDisabledFilter(this, selectedProjectType) || shouldReinit;
    });

    if (shouldReinit) {
        InitExtFilters(containerId);
    }
}

function ToggleProjectTypeDisabledFilter(obj, selectedProjectType) {
    if (!obj)
        return false;

    const $obj = jQuery(obj);
    const disabledOnProjectTypes = $obj.attr("data-disabled-on-project-types");

    if (!disabledOnProjectTypes)
        return false;

    const shouldHide = IsProjectTypeMatch(selectedProjectType, disabledOnProjectTypes);
    const wasHidden = !$obj.is(":visible");

    if (shouldHide) {
        const filterExt = $obj.find("[data-type='filter-ext']")[0];
        if (filterExt) {
            ClearFilter(filterExt);
        }
        $obj.hide();
        return false;
    }

    $obj.show();
    return wasHidden;
}

function IsProjectTypeMatch(selectedProjectType, disabledOnProjectTypes) {
    if (!selectedProjectType || !disabledOnProjectTypes)
        return false;

    let selected = NormalizeProjectTypeValue(selectedProjectType);
    let configuredValues = disabledOnProjectTypes
        .split("|")
        .map(function (item) { return NormalizeProjectTypeValue(item); })
        .filter(function (item) { return item !== ""; });

    return configuredValues.indexOf(selected) >= 0;
}

function NormalizeProjectTypeValue(value) {
    return (value || "")
        .toString()
        .trim()
        .toLowerCase()
        .replace(/[-\s]+/g, "");
}

function GetSelectedProjectTypeValue() {
    let ctl = jQuery("#ProjectTransition_ProjectTypesTabs");
    if (!ctl || ctl.length === 0)
        return "";

    return (ctl.val() || "").toString().trim();
}

function setMemoryState() {


    var memoryState = getMemoryStateTuple();



    var gridId = "ProjectTransition";

    let filters = jQuery("#" + gridId).find("[data-type='filter']");



    extFiltersContainter = "projTransitionExtFilters";

    let allFilters = filters;
    if (extFiltersContainter != null) {
        let extFilters = jQuery("#" + extFiltersContainter).find("[data-type='filter-ext']");
        if (extFilters != null) {
            let fLen = extFilters.length;
            for (let i = 0; i < fLen; i++) {
                allFilters.push(extFilters[i]);
            }
        }
    }

    //if provided object is a paginator, use its value, otherwise pick any paginator
    let paginator = null;
    let dataType = "filters";

    paginator = getAPaginatorObj("ProjectTransition");

    var model = BuildRefreshRequestModel(
        gridId, filters,
        paginator);


    var modelStr = JSON.stringify(model)
    sessionStorage.setItem(memoryState, modelStr);



}

function getMemoryState() {

    var memoryState = getMemoryStateTuple();
    model = JSON.parse(sessionStorage.getItem(memoryState));


    return model;



}



function getMemoryStateTuple() {
    var primaryTabName = jQuery("#ProjectTransition_ReportType").val();
    var currentFilterTab = jQuery("#ProjectTransition_ProjectTypesTabs").val();
    var hiddenTab = jQuery("#ProjectTransition_HiddenTab").val();

    var memoryState = [primaryTabName, currentFilterTab, hiddenTab];

    return memoryState;
}


function insertHiddenFilter() {
    htmlToUse = '<input style="display:none" data-type="filter-ext" data-filter-type="enSingleTextFilter" data-grid-id="ProjectTransition" data-search="HiddenTab" id="ProjectTransition_HiddenTab" name="search" type="search" filter-watermark="" value="Desc">'
    extFiltersContainter = "projTransitionExtFilters";
    jQuery("#" + extFiltersContainter).append(htmlToUse);
}



function SwitchClusterReport(obj) {
    switchPrimaryTab("ClusterReport");
}

function SwitchSISReport(obj) {
    switchPrimaryTab("SISReport");

}

function SwitchNUCRAReport(obj) {
    switchPrimaryTab("NUCRA");

}




function switchPrimaryTab(primaryTabName) {

    removeSessionMemory();

    setMemoryState();

    var gridId = "ProjectTransition";
    let filters = jQuery("#" + gridId).find("[data-type='filter']");

    jQuery("#ProjectTransition_ReportType").val(primaryTabName);



    extFiltersContainter = "projTransitionExtFilters";

    let allFilters = filters;
    if (extFiltersContainter != null) {
        let extFilters = jQuery("#" + extFiltersContainter).find("[data-type='filter-ext']");
        if (extFilters != null) {
            let fLen = extFilters.length;
            for (let i = 0; i < fLen; i++) {
                allFilters.push(extFilters[i]);
            }
        }
    }


    //add external filters for Nucra, they'll be sorted out in the server
    extFilters = jQuery("#NucraGridFilters").find("[data-type='filter-ext']");
    if (extFilters != null) {
        let fLen = extFilters.length;
        for (let i = 0; i < fLen; i++) {
            allFilters.push(extFilters[i]);
        }
    }


    //if provided object is a paginator, use its value, otherwise pick any paginator
    let paginator = null;
    let dataType = "filters";

    var memoryState = getMemoryState();


    if (memoryState == null) {
        var model = BuildRefreshRequestModel(
            gridId, filters,
            paginator);


        model['PrimaryTab'] = primaryTabName;//"ClusterReport";
    }

    else {
        var model = memoryState;
    }


    SendRequestProjectTransition(model, gridId, function () {
        ReinitGrid(gridId);
        jQuery("#" + gridId).find("[img-sort-type='asc']").addClass("grid-hidden");
        jQuery("#" + gridId).find("[img-sort-type='desc']").addClass("grid-hidden");

        if (primaryTabName == "ClusterReport" /*|| primaryTabName == "NUCRA"*/) {
            jQuery(".dynamic-export-view").addClass("ClusterReport");
            jQuery("#projTransitionExtFilters").css("display", "none");
            jQuery("#ProjectTransition > div > .tabs.ui-tabs").css("visibility", "hidden");
            jQuery("#ProjectTransition > div > .tabs.ui-tabs").css("display", "none");
            jQuery("#txtSISReportText").css("visibility", "hidden");
            jQuery(".pagination-section").css("display", "none");
            jQuery("#ProjectTransition table").css("min-height", "fit-content");
            jQuery("#transition-projects_exportExcelFiltered").show();
            jQuery("#transition-projects_exportXMLFiltered").show();
            jQuery("#transition-projects_filtered_text").show()
            jQuery("#NucraGridFilters").css("display", "none");

        }
        else if (primaryTabName == "NUCRA") {
            //jQuery(".dynamic-export-view").addClass("ClusterReport");
            jQuery(".dynamic-export-view").removeClass("ClusterReport");
            jQuery("#NucraGridFilters").css("display", "block");
            jQuery("#projTransitionExtFilters").css("display", "none");
            jQuery("#ProjectTransition > div > .tabs.ui-tabs").css("visibility", "hidden");
            jQuery("#ProjectTransition > div > .tabs.ui-tabs").css("display", "none");
            jQuery("#txtSISReportText").css("visibility", "hidden");
            //jQuery(".pagination-section").css("display", "none");
            jQuery("#ProjectTransition table").css("min-height", "fit-content");
            jQuery("#transition-projects_exportExcelFiltered").show();
            jQuery("#transition-projects_exportXMLFiltered").show();
            jQuery("#transition-projects_filtered_text").show()
            jQuery("#NucraGridFilters").show()
        }
        else {
            jQuery(".dynamic-export-view").removeClass("ClusterReport");
            jQuery("#projTransitionExtFilters").css("display", "block");
            jQuery("#NucraGridFilters").css("display", "none");
            jQuery("#ProjectTransition > div > .tabs.ui-tabs").css("visibility", "visible");
            jQuery("#ProjectTransition > div > .tabs.ui-tabs").css("display", "block");
            jQuery("#txtSISReportText").css("visibility", "visible");
            jQuery(".pagination-section").css("display", "block");
            var table = jQuery("#ProjectTransition table")[0];
            table.style.removeProperty("min-height");

            if (jQuery("#ProjectTransition_ProjectTypesTabs").val() == 'Select Project Type') {
                jQuery("#transition-projects_exportExcelFiltered").hide();
                jQuery("#transition-projects_exportXMLFiltered").hide();
                jQuery("#transition-projects_filtered_text").hide();
            }
        }
        SetXMLProjTransition();
        ActivateCorrectTab();

    });


}


function ActivateCorrectTab() {

    var primaryTabName = jQuery("#ProjectTransition_ReportType").val();

    if (primaryTabName == "SISReport") {
        jQuery("#SISReport").attr("class", "active")
        jQuery("#ClusterReport").attr("class", "")
        jQuery("#NUCRA").attr("class", "")
    }
    if (primaryTabName == "ClusterReport") {
        jQuery("#SISReport").attr("class", "")
        jQuery("#ClusterReport").attr("class", "active")
        jQuery("#NUCRA").attr("class", "")
    }
    if (primaryTabName == "NUCRA") {
        jQuery("#SISReport").attr("class", "")
        jQuery("#ClusterReport").attr("class", "")
        jQuery("#NUCRA").attr("class", "active")
    }

}

function openDocument(documentLink) {
    if (documentLink != "") {
        documentLink = window.location.origin + "/" + documentLink.replaceAll("\\", "/")
        window.open(documentLink, '_blank').focus();
    }
}

function SetXMLProjTransition() {
    ///Media/Planning/queues-data/transitionProjects.xml
    var primaryTab = jQuery("#ProjectTransition_ReportType").val();

    var base = window.location.origin + "/"
    if (primaryTab == "SISReport") {
        jQuery("#transitionProjectXmlDownloader").attr("href", base + "pub/planning/downloads/xml/transitionProjects.xml")
    }
    else if (primaryTab == "ClusterReport") {
        jQuery("#transitionProjectXmlDownloader").attr("href", base + "pub/planning/downloads/xml/clusterReports.xml")
    }
    else if (primaryTab == "NUCRA") {
        jQuery("#transitionProjectXmlDownloader").attr("href", base + "pub/planning/downloads/xml/NUCRA.xml")
    }


}


function SendRequestProjectTransition(model, gridId, _callback) {

    let modelStr = JSON.stringify(model);
    //alert(modelStr);

    let url = getBaseUrl(gridId);

    jQuery.post(url, { jsonModel: modelStr }, function (result) {
        jQuery("#" + gridId).html(result);
        _callback();
    });


}

function SendRequestProjectTransitionWithSearchModel(model, searchModel, gridId, _callback) {
    let searchModelStr = JSON.stringify(searchModel);

    let modelStr = JSON.stringify(model);
    //alert(modelStr);

    let url = getBaseUrl(gridId);

    jQuery.post(url, { jsonModel: modelStr, primarySearchFilterJson: searchModelStr }, function (result) {
        jQuery("#" + gridId).html(result);
        _callback();
    });


}

function ReinitGrid() {
    ctl = document.getElementById("projTransitionExtFilters");
    let gridId = ctl.getAttribute("grid-id");
    InitFilters(gridId);

    ctl = document.getElementById("NucraGridFilters");
    let gridIdNucra = ctl.getAttribute("grid-id");
    InitFilters(gridIdNucra);
}


function GetSorting() {
    let modelSortValue = "";
    let modelSortDir = "";
    let ctl = document.getElementById("projTransitionExtFilters");
    let gridId = ctl.getAttribute("grid-id");
    let sortItems = jQuery("#" + gridId).find("[data-type='sortOrder']");
    if (sortItems != null) {
        let len = sortItems.length;
        for (let i = 0; i < len; i++) {
            let sortDir = sortItems[i].getAttribute("data-sort-dir");
            if (sortDir != null && sortDir != "none") {
                modelSortDir = sortDir;
                modelSortValue = sortItems[i].getAttribute("data-sort");
                modelSortElement = sortItems[i];
                break;
            }
        }
    }

    if (typeof modelSortElement === undefined || typeof modelSortElement === 'undefined') {
        return [modelSortDir, modelSortValue, null];
    }
    return [modelSortDir, modelSortValue, modelSortElement];
}

function SetSortNoRefresh(obj) {
    if (obj == null)
        return;

    let gridId = obj.getAttribute("data-grid-id");
    let selItemSortDir = obj.getAttribute("data-sort-dir");

    //remove all previous sorting
    let sortItems = jQuery("#" + gridId).find("[data-type='sortOrder']");
    if (sortItems == null)
        return;
    let fLen = sortItems.length;
    for (let i = 0; i < fLen; i++) {
        sortItems[i].setAttribute("data-sort-dir", "none");
        //reset the sorting icons
        jQuery(sortItems[i]).find("input").addClass("grid-hidden");
        //jQuery(sortItems[i]).find("input").attr("hidden", false);
        jQuery(sortItems[i]).find("[img-sort-type=none]").removeClass("grid-hidden");
    }

    //if current column was already sorted desc, then switch with asc
    if (selItemSortDir == 'desc') {
        jQuery(obj).find("[img-sort-type=desc]").removeClass("grid-hidden");
        jQuery(obj).find("[img-sort-type=none]").addClass("grid-hidden");
    }
    else {
        jQuery(obj).find("[img-sort-type=asc]").removeClass("grid-hidden");
        jQuery(obj).find("[img-sort-type=none]").addClass("grid-hidden");
    }

    obj.setAttribute("data-sort-dir", selItemSortDir);
}

//not in use
function DownloadProjConstXL(obj) {
    if (obj == null)
        return;

    //jQuery('#loader').fadeOut('fast');


    let gridId = obj.getAttribute("data-grid-id");
    //console.log("gridId="+ gridId);
    //let filters = $("#"+gridId).find(".filter");
    let filters = jQuery("#" + gridId).find("[data-type='filter']");


    let extFilters = jQuery("#" + gridId).find("[data-type='filter-ext']");
    if (extFilters != null) {
        let fLen = extFilters.length;
        for (let i = 0; i < fLen; i++) {
            filters.push(extFilters[i]);
        }
    }


    //if provided object is a paginator, use its value, otherwise pick any paginator
    let paginator = null;
    let dataType = obj.getAttribute("data-type");
    if (dataType == "paginator") {
        paginator = obj;
    }
    else {
        paginator = getAPaginatorObj(gridId);
    }

    let model = BuildRefreshRequestModel(gridId, filters, paginator);

    let modelStr = JSON.stringify(model);
    let url = "/m/ProjectConst/GetUpgradesXL" + "?jsonModel=" + modelStr;
    //jQuery(this).attr("href", url);
    jQuery.get(url);
    return false;
    //window.open(url , '_blank');

    //    if (bodyOnly) {
    //        SetPartialRefreshFlag(gridId, true);
    //        SendBodyRequest(BuildRefreshRequestModel(gridId, filters, paginator), gridId);
    //    }
    //    else {
    //        SetPartialRefreshFlag(gridId, false);
    //        SendRequest(BuildRefreshRequestModel(gridId, filters, paginator), gridId);
    //    }
}

//handles descriptions for upgrade id, cost allocation, required date, actual in service, & projected in service.
function OpenModalInfo(description, container) {
    jQuery(container).find("img[alt='Info']").attr("src", "/assets/MVC/images/additional-information-hover.jpg");
    jQuery('#modalInfo').css('display', 'block');
    jQuery('#infoDescriptionId').html(description);
    let rect = container.getBoundingClientRect();
    let x = rect.left + window.scrollX;
    let y = rect.top + rect.height + 5 + window.scrollY;
    //console.log('x='+rect.x + ', y=' +rect.y);
    infoModalMouseEnterAction('#modalInfo', x, y);
}
function CloseModalInfo() {
    //cleanup & close modal
    jQuery('#modalInfo').css('display', 'none');
    jQuery('#infoDescriptionId').html('');
    jQuery("img[alt='Info']").attr("src", "/assets/MVC/images/additional-information.jpg");
}

function OpenUpgradeIdInfo(container) {
    let ctl = document.getElementById("hidProjectTransition_infoUpgradeId");
    let description = ctl.value;
    OpenModalInfo(description, container);
}

function OpenCostAllocationInfo(container) {
    let ctl = document.getElementById("hidProjectTransition_CostAllocation");
    let description = ctl.value;
    OpenModalInfo(description, container);
}

function OpenRequiredDateInfo(container) {
    let ctl = document.getElementById("hidProjectTransition_RequiredDate");
    let description = ctl.value;
    OpenModalInfo(description, container);
}

function OpenRequiredDateInfo(container) {
    let ctl = document.getElementById("hidCostAlloc_RequiredDate");
    let description = ctl.value;
    OpenModalInfo(description, container);
}

function OpenProjectedInServiceInfo(container) {
    let ctl = document.getElementById("hidCostAlloc_ProjectedInserviceDate");
    let description = ctl.value;
    OpenModalInfo(description, container);
}

function OpenActualInServiceInfo(container) {
    let ctl = document.getElementById("hidCostAlloc_ActualInServiceDate");
    let description = ctl.value;
    OpenModalInfo(description, container);
}

function OpenSISReportDetails(id, container) {

    let ctl = document.getElementById("sisReportDetails");
    //let ctlContent = document.getElementById("SISReportDetailsContent");
    let successFlag = true;
    let url = "/m/ProjectTransition/SISReportDetails" + "?queueNumber=" + id;
    (jQuery(ctl)).load(url, function (response, status, xhr) {
        if (status != "success") {
            //enable next row for debugging
            //jQuery("#error").html(response);
            let errMsg = "Failed to open project details (queueNumber=" + id + "): " + xhr.status + " - " + xhr.statusText;
            console.error(errMsg);
            successFlag = false;
        }
        else {

        }

        if (successFlag) {
            //update the location of the control if it's being passed
            if (container != null) {
                jQuery(ctl).css('display', 'block');
            }
        }

    });

    ////todo - getelementbyid needs to be replaced by finding id among children of the control
    //let txtCtl = document.getElementById("txtUpgrId");
    //txtCtl.innerHTML=id;
    //txtCtl = document.getElementById("txtDriver");
    //txtCtl.innerHTML=driver;
    //ctl.style.display = "block";
}


function OpenSISReportDetailsForLTF(id, container) {

    let ctl = document.getElementById("sisReportDetails");
    let successFlag = true;
    let url = "/m/ProjectTransition/SISReportDetailsForLTF" + "?queueNumber=" + id;
    (jQuery(ctl)).load(url, function (response, status, xhr) {
        if (status != "success") {
            let errMsg = "Failed to open project details (queueNumber=" + id + "): " + xhr.status + " - " + xhr.statusText;
            console.error(errMsg);
            successFlag = false;
        }
        else {

        }

        if (successFlag) {
            if (container != null) {
                jQuery(ctl).css('display', 'block');
            }
        }
    });
}

function CloseSISReportDetails() {
    //cleanup
    let ctl = document.getElementById("sisReportDetails");
    ctl.style.display = "none";
}
function OpenClusterReportDetails(id, container) {

    let ctl = document.getElementById("clusterReportDetails");
    //let ctlContent = document.getElementById("SISReportDetailsContent");
    let successFlag = true;
    let url = "/m/ProjectTransition/ClusterReportDetails" + "?cycleName=" + id;
    (jQuery(ctl)).load(url, function (response, status, xhr) {
        if (status != "success") {
            //enable next row for debugging
            //jQuery("#error").html(response);
            let errMsg = "Failed to open project details (cycleName=" + id + "): " + xhr.status + " - " + xhr.statusText;
            console.error(errMsg);
            successFlag = false;
        }
        else {

        }

        if (successFlag) {
            //update the location of the control if it's being passed
            if (container != null) {
                jQuery(ctl).css('display', 'block');
            }
        }

    });

    ////todo - getelementbyid needs to be replaced by finding id among children of the control
    //let txtCtl = document.getElementById("txtUpgrId");
    //txtCtl.innerHTML=id;
    //txtCtl = document.getElementById("txtDriver");
    //txtCtl.innerHTML=driver;
    //ctl.style.display = "block";
}

function CloseClusterReportDetails() {
    //cleanup
    let ctl = document.getElementById("clusterReportDetails");
    ctl.style.display = "none";
}

function OpenNucraProjectDetails(id, container) {

    let ctl = document.getElementById("nucraProjectDetails");
    //let ctlContent = document.getElementById("SISReportDetailsContent");
    let successFlag = true;
    let url = "/m/ProjectTransition/NucraProjectDetails" + "?upgradeId=" + id;
    (jQuery(ctl)).load(url, function (response, status, xhr) {
        if (status != "success") {
            //enable next row for debugging
            //jQuery("#error").html(response);
            let errMsg = "Failed to open project details (upgradeid=" + id + "): " + xhr.status + " - " + xhr.statusText;
            console.error(errMsg);
            successFlag = false;
        }
        else {

        }

        if (successFlag) {
            //update the location of the control if it's being passed
            if (container != null) {
                jQuery(ctl).css('display', 'block');
            }
        }
    });
}

function CloseNucraProjectDetails() {
    //cleanup
    let ctl = document.getElementById("nucraProjectDetails");
    ctl.style.display = "none";
}


function replaceText(id) {
    OpenUpgradeDetails(id)
}

function OpenCostAllocationDetails(id, values) {

    //converted to jQuery
    jQuery("#costAllocUpgrId").html(id);
    jQuery("#costAllocationDetails").css('display', 'block');

    //List out all Cost Allocation Percents in the modal.
    if (values) {
        let costAllocationPercentList = values.split(",");
        for (var costAllocationPercentItem of costAllocationPercentList) {
            var costAllocationPercentSubstringsList = costAllocationPercentItem.split(/(:)/);
            //create individual spans of cost allocation percent items wrapped around a div.
            //set title and value to each span i.e. Title =  AEC: & Value = 3.99
            var costAllocationPercentOuterDiv = jQuery('<div/>', {
                class: 'costAllocationPercentItem'
            }).appendTo("#costAllocDetailsBodyId");
            jQuery('<span/>', {
                html: (costAllocationPercentSubstringsList[0] + costAllocationPercentSubstringsList[1]).bold()
            }).appendTo(costAllocationPercentOuterDiv);
            jQuery('<span/>', {
                html: costAllocationPercentSubstringsList[2]
            }).appendTo(costAllocationPercentOuterDiv);
        }
    }
}

function OpenContingentProjectDetails(id) {

    let ctl = document.getElementById("contingentProjectDetails");
    let url = "/m/ProjectTransition/UpgradeContingentProject" + "?upgradeId=" + id;
    (jQuery(ctl)).load(url, function (response, status, xhr) {
        if (status != "success") {
            //enable next row for debugging
            //jQuery("#error").html(response);
            let errMsg = "Failed to open contingent project details (upgradeId=" + id + "): " + xhr.status + " - " + xhr.statusText;
            console.error(errMsg);
        }
        else {
            jQuery("#contingentProjectDetails").css('display', 'block');
        }
    });
}

function CloseContingentProjectDetails() {
    //cleanup
    jQuery("#contingentProjectDetails").css('display', 'none');
    jQuery('#contingentProjectDetailsBodyId').html('');
}

function OpenProjectsWithCostAllocDetails(id) {

    let ctl = document.getElementById("projectsWithCostAllocDetails");
    let url = "/m/ProjectTransition/UpgradeProjectsWithCostAlloc" + "?upgradeId=" + id;
    (jQuery(ctl)).load(url, function (response, status, xhr) {
        if (status != "success") {
            //enable next row for debugging
            //jQuery("#error").html(response);
            let errMsg = "Failed to open project cost allocation details (upgradeId=" + id + "): " + xhr.status + " - " + xhr.statusText;
            console.error(errMsg);
        }
        else {
            jQuery("#projectsWithCostAllocDetails").css('display', 'block');
        }
    });
}

function CloseProjectsWithCostAllocDetails() {
    //cleanup
    jQuery("#projectsWithCostAllocDetails").css('display', 'none');
    jQuery('#projectsWithCostAllocDetailsBodyId').html('');
}

//status info
function OpenStatusInfo(container) {

    //let ctl = document.getElementById("statusInfo");
    //modalCtl.show();
    //modalCtl.modal("show");
    //ctl.style.display = "block";
    //converted to jQuery
    jQuery('#statusInfo').css('display', 'block');
    jQuery(container).find("img[alt='Info']").attr("src", "/assets/MVC/images/additional-information-hover.jpg");
    //infoModalMouseHoverAction('#statusInfo');
    let rect = container.getBoundingClientRect();
    let x = rect.left + window.scrollX;
    let y = rect.top + rect.height + 5 + window.scrollY;
    infoModalMouseEnterAction('#statusInfo', x, y);

}
function CloseStatusInfo() {

    //cleanup
    //let ctl = document.getElementById("statusInfo");
    //ctl.style.display = "none";
    //converted to jQuery
    jQuery('#statusInfo').css('display', 'none');
    jQuery("img[alt='Info']").attr("src", "/assets/MVC/images/additional-information.jpg");
}

function infoModalMouseEnterAction(selector, x, y) {

    jQuery(selector).css('left', x);
    jQuery(selector).css('top', y);
    jQuery('.info-modal-content').css('margin', 0);
    jQuery(selector).css("position", "absolute");

}


//function infoModalMouseHoverAction(selector) {
//    jQuery(document).mouseenter(function (e) {
//        jQuery(selector).css('left', e.pageX);
//        jQuery(selector).css('top', e.pageY + 15);
//        jQuery('.info-modal-content').css('margin', 0);
//        jQuery(selector).css("position", "absolute");
//    });
//}

jQuery(function () {
    jQuery('.transition-projects-exportToXls').on('click',
        //picks up all the filters settings and sends a post request to generate an Excel file, then downloads it    
        function (event) {
            //Create a search/pagination model
            let obj = event.currentTarget;
            let gridId = obj.getAttribute("data-grid-id");
            let filters = jQuery("#" + gridId).find("[data-type='filter']");

            let extFiltersId = obj.getAttribute("ext-filters-id");
            let extFilters = jQuery("#" + extFiltersId).find("[data-type='filter-ext']");
            if (extFilters != null) {
                let fLen = extFilters.length;
                for (let i = 0; i < fLen; i++) {
                    filters.push(extFilters[i]);
                }
            }
            //add external filters for Nucra, the'll be sorted out in the server
            //if (extFiltersContainter != null) {
            extFilters = jQuery("#NucraGridFilters").find("[data-type='filter-ext']");
            if (extFilters != null) {
                let fLen = extFilters.length;
                for (let i = 0; i < fLen; i++) {
                    filters.push(extFilters[i]);
                }
            }
            //}

            //if provided object is a paginator, use its value, otherwise pick any paginator
            let paginator = null;
            let dataType = obj.getAttribute("data-type");
            if (dataType == "paginator") {
                paginator = obj;
            }
            else {
                paginator = getAPaginatorObj(gridId);
            }

            let model = BuildRefreshRequestModel(gridId, filters, paginator);
            let modelStr = JSON.stringify(model);

            var url = "";

            var option = obj.getAttribute("data-grid-xls");

            if (option == "filtered") {
                var url = "/m/ProjectTransition/GenerateExcelTransitionProjects";
            }
            else if (option == "all") {
                var url = "/m/ProjectTransition/GenerateExcelTransitionProjectsAll";
            }


            var primaryTab = jQuery("#ProjectTransition_ReportType").val();

            if (primaryTab == "ClusterReport") {
                if (option == "filtered") {
                    var url = "/m/ProjectTransition/GenerateExcelClusterReports";
                }
                else if (option == "all") {
                    var url = "/m/ProjectTransition/GenerateExcelTransitionProjectsClusterAll";
                }
            }

            if (primaryTab == "NUCRA") {
                if (option == "filtered") {
                    var url = "/m/ProjectTransition/GenerateExcelNUCRAProjects";
                }
                else if (option == "all") {
                    var url = "/m/ProjectTransition/GenerateExcelNUCRAProjectsAll";
                }
            }


            var request = new XMLHttpRequest();
            request.open('POST', url, true);
            request.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
            request.responseType = 'blob';


            request.onload = function () {
                // Handle status code 200 - trigger download
                if (request.status === 200) {
                    // Try to find out the filename from the content disposition `filename` value
                    //var disposition = request.getResponseHeader('content-disposition');
                    //var matches = /"([^"]*)"/.exec(disposition);
                    //var filename = (matches != null && matches[1] ? matches[1] : 'file.pdf');

                    // The actual download
                    var blob = new Blob([request.response], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
                    var link = document.createElement('a');
                    link.href = window.URL.createObjectURL(blob);

                    var primaryTab = jQuery("#ProjectTransition_ReportType").val();

                    var initialFileName = "";
                    if (primaryTab == "SISReport") {
                        initialFileName = "CycleProjects";
                    }
                    else if (primaryTab == "NUCRA") {
                        initialFileName = "NucraProjects";
                    }

                    if (option == "filtered") {
                        initialFileName += "-Filtered.xlsx";
                    }
                    else if (option == "all") {
                        initialFileName += "-All.xlsx";
                    }

                    link.download = initialFileName;
                    console.log(link.download);

                    //document.body.appendChild(link);
                    link.click();
                    //document.body.removeChild(link);
                }
                else { //any other status
                    let errMsg = "Failed to download Project Transition Excel File Status: " +
                        request.status + " - " + request.statusText;

                    console.error(errMsg);
                }
            };
            request.send('jsonModel=' + modelStr);

        });
});

jQuery('.transition-projects-exportToXml').on('click',
    //picks up all the filters settings and sends a post request to generate an Excel file, then downloads it    
    function (event) {
        //Create a search/pagination model
        let obj = event.currentTarget;
        let gridId = obj.getAttribute("data-grid-id");
        let filters = jQuery("#" + gridId).find("[data-type='filter']");

        let extFiltersId = obj.getAttribute("ext-filters-id");
        let extFilters = jQuery("#" + extFiltersId).find("[data-type='filter-ext']");
        if (extFilters != null) {
            let fLen = extFilters.length;
            for (let i = 0; i < fLen; i++) {
                filters.push(extFilters[i]);
            }
        }
        //add external filters for Nucra, the'll be sorted out in the server
        //if (extFiltersContainter != null) {
        extFilters = jQuery("#NucraGridFilters").find("[data-type='filter-ext']");
        if (extFilters != null) {
            let fLen = extFilters.length;
            for (let i = 0; i < fLen; i++) {
                filters.push(extFilters[i]);
            }
        }
        //}

        //if provided object is a paginator, use its value, otherwise pick any paginator
        let paginator = null;
        let dataType = obj.getAttribute("data-type");
        if (dataType == "paginator") {
            paginator = obj;
        }
        else {
            paginator = getAPaginatorObj(gridId);
        }

        let model = BuildRefreshRequestModel(gridId, filters, paginator);
        let modelStr = JSON.stringify(model);

        var url = "";

        var option = obj.getAttribute("data-grid-xml");

        if (option == "filtered") {
            var url = "/m/ProjectTransition/GenerateXMLTransitionProjects";
        }
        else if (option == "all") {
            var url = "/m/ProjectTransition/GenerateXMLTransitionProjectsAll";
        }


        var primaryTab = jQuery("#ProjectTransition_ReportType").val();
        if (primaryTab == "ClusterReport") {
            if (option == "filtered") {
                var url = "/m/ProjectTransition/GenerateXMLTransitionProjectsCluster";
            }
            else if (option == "all") {
                var url = "/m/ProjectTransition/GenerateXMLTransitionProjectsClusterAll";
            }
        }

        if (primaryTab == "NUCRA") {
            if (option == "filtered") {
                var url = "/m/ProjectTransition/GenerateXMLNUCRAProjects";
            }
            else if (option == "all") {
                var url = "/m/ProjectTransition/GenerateXMLNUCRAProjectsAll";
            }
        }

        var request = new XMLHttpRequest();
        request.open('POST', url, true);

        request.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
        request.responseType = 'blob';



        request.onload = function () {
            // Handle status code 200 - trigger download
            if (request.status === 200) {
                // Try to find out the filename from the content disposition `filename` value
                //var disposition = request.getResponseHeader('content-disposition');
                //var matches = /"([^"]*)"/.exec(disposition);
                //var filename = (matches != null && matches[1] ? matches[1] : 'file.pdf');

                // The actual download
                var blob = new Blob([request.response], { type: 'text/xml' });
                var link = document.createElement('a');
                link.href = window.URL.createObjectURL(blob);

                var primaryTab = jQuery("#ProjectTransition_ReportType").val();

                if (primaryTab == "SISReport") {
                    if (option == "filtered") {
                        link.download = "CycleProjects-Filtered.xml";
                    }
                    else if (option == "all") {
                        link.download = "CycleProjects-All.xml";
                    }

                }

                if (primaryTab == "NUCRA") {
                    if (option == "filtered") {
                        link.download = "NucraProjects-Filtered.xml";
                    }
                    else if (option == "all") {
                        link.download = "NucraProjects-All.xml";
                    }

                }

                console.log(link.download);

                //document.body.appendChild(link);
                link.click();
                //document.body.removeChild(link);
            }
            else { //any other status
                let errMsg = "Failed to download Project Transition Excel File Status: " +
                    request.status + " - " + request.statusText;

                console.error(errMsg);
            }
        };

        request.send('jsonModel=' + modelStr);


    });
;
