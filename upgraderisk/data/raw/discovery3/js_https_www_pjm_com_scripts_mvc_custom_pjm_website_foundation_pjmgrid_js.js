/********************************/
/********* PJM Grid *************/
/********************************/


/************* Grid ***************/

function NormalizeFilter(selectBoxName, vsbMenu) {

    let items = jQuery("#" + selectBoxName + " > option[value='all']");
    if (items.length > 1) {
        items[0].remove();
    }
    //pretty strange solution to compensate extra "All" checkboxes that the control has
    let items3 = jQuery(vsbMenu).find("li[value='all']");
    if (items3.length > 2) {
        items3[0].remove();
        items3[1].remove();
    }
    if (items3.length > 1) {
        items3[0].remove();
    }
}

function InitSelectionBox( selectBoxName, disableSelectAll=false, searchFlag=false, watermark="", allAlias = "All") {
        let selectBox = new vanillaSelectBox("#" + selectBoxName, {maxSelect: 1, "disableSelectAll": disableSelectAll, "maxHeight": 200, "maxWidth": 200, minwidth:60, "search": searchFlag, placeHolder: watermark, "translations": { "all": allAlias, "items": "items","selectAll":"All","clearAll":"All"}});

        //Add click events on options selection
        let selectBox3 = document.getElementById(selectBoxName);
        var element = selectBox3.nextSibling;
        var foundVSBMenuItems = element.getElementsByClassName("vsb-menu");
        if (foundVSBMenuItems.length > 0) {
            NormalizeFilter(selectBoxName, foundVSBMenuItems);
        }

        ////remove the event if was added before
        //jQuery("#" + selectBox3.id).off("change");
        ////add event
        selectBox3.addEventListener("change", function (e) {
	        RefreshGrid(selectBox3, true);
        });
    }

    function InitExtSelectionBox( selectBoxName, containerId, disableSelectAll=false, searchFlag=false, watermark="", allAlias = "All") {
        let selectBox = new vanillaSelectBox("#" + selectBoxName, {maxSelect: 1,"disableSelectAll": disableSelectAll, "maxHeight": 200, "maxWidth": 200, "search": searchFlag, placeHolder: watermark, "translations": { "all": allAlias, "items": "items","selectAll":"All","clearAll":"All"}});

        //Add click events on options selection
        let selectBox3 = document.getElementById(selectBoxName);
        var element = selectBox3.nextSibling;
        var foundVSBMenuItems = element.getElementsByClassName("vsb-menu");
        if (foundVSBMenuItems.length > 0) {
            NormalizeFilter(selectBoxName, foundVSBMenuItems);
        }

        //remove the event if was added before
        //jQuery("#" + selectBox3.id).off("change");
        //add event
        selectBox3.addEventListener("change", function (e) {
	        RefreshGridWithExtFilters(selectBox3, containerId);
        });
    }

function InitFilters(gridId) {

    let filters = jQuery("#"+gridId).find("[data-type='filter']");
    let fLen = filters.length;
    for (let i = 0; i < fLen; i++) {
        let isSingleSelect = filters[i].getAttribute("data-single-select");
        let dataFilterType = filters[i].getAttribute("data-filter-type");
        let watermark = filters[i].getAttribute("filter-watermark");
        if (dataFilterType == "enMultipleTextsFilter" &&
            isSingleSelect !=null && isSingleSelect == "False") {
            InitSelectionBox(filters[i].id, false, true, watermark);
        }
    }
}

function InitExtFilters(objId) {

    let filters = jQuery("#"+objId).find("[data-type='filter-ext']");
    let fLen = filters.length;
    for (let i = 0; i < fLen; i++) {
        let isSingleSelect = filters[i].getAttribute("data-single-select");
        let dataFilterType = filters[i].getAttribute("data-filter-type");
        let watermark = filters[i].getAttribute("filter-watermark");
        if (dataFilterType == "enMultipleTextsFilter" &&
            isSingleSelect !=null && isSingleSelect == "False") {
            let containerId = filters[i].getAttribute("filter-container");
            if (containerId != null)
                InitExtSelectionBox(filters[i].id, containerId, false, false, watermark);
        }
    }
}

function HandleExtFilterEnter(obj, filtersConId, e) {
    if (e.keyCode == '13') {
        if (obj != null)
            RefreshGridWithExtFilters(obj,filtersConId);
        e.preventDefault();
    }
}

function HandleFilterEnter(obj, e) {
    if (e.keyCode == '13') {
        if (obj != null)
            RefreshGrid(obj);
        e.preventDefault();
    }
}

//Refresh only the body of the table
function HandleFilterEnterBody(obj, e) {
    if (e.keyCode == '13') {
        if (obj != null)
            RefreshGrid(obj, true);
        e.preventDefault();
    }
}

function RefreshGrid(obj, bodyOnly = false, resetCurrPage = true) {
    if (obj == null)
        return;

    //jQuery('#loader').fadeOut('fast');

    let gridId = obj.getAttribute("data-grid-id");

    //reset the current page to 1 if needed
    if (resetCurrPage == true) {
        SetPaginatorsAttribute(gridId,"data-current-page",1);
    }

    let filters = jQuery("#"+gridId).find("[data-type='filter']");
    let extFilters = jQuery("[data-type='filter-ext'][data-grid-id='" + gridId + "']");
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
    
    if (bodyOnly) {
        SetPartialRefreshFlag(gridId, true);
        SendBodyRequest(BuildRefreshRequestModel(gridId, filters, paginator), gridId);
    }
    else {
        SetPartialRefreshFlag(gridId, false);
        SendRequest(BuildRefreshRequestModel(gridId, filters, paginator), gridId);
    }
}



//extFilters - list of the external filters
function RefreshGridWithExtFilters(obj, extFiltersContainter, bodyOnly = true, resetCurrPage = true) {
    if (obj == null)
        return;

    //jQuery('#loader').fadeOut('fast');
    let gridId = obj.getAttribute("data-grid-id");
    if (resetCurrPage == true) {
        SetPaginatorsAttribute(gridId,"data-current-page",1);
    }
    let filters = jQuery("#"+gridId).find("[data-type='filter']");
    let allFilters = filters;
    if (extFiltersContainter != null) {
        let extFilters = jQuery("#"+extFiltersContainter).find("[data-type='filter-ext']");
        if (extFilters != null) {
            let fLen = extFilters.length;
            for (let i = 0; i < fLen; i++) {
                allFilters.push(extFilters[i]);
            }
        }
    }
    let paginator = getAPaginatorObj(gridId);
    //SendBodyRequest(BuildRefreshRequestModel(gridId, allFilters, paginator), gridId);

    if (bodyOnly) {
        SetPartialRefreshFlag(gridId, true);
        SendBodyRequest(BuildRefreshRequestModel(gridId, allFilters, paginator), gridId);
    }
    else {
        SetPartialRefreshFlag(gridId, false);
        SendRequest(BuildRefreshRequestModel(gridId, allFilters, paginator), gridId);
    }

}

function ResetGrid(gridId) {
    if (gridId == null)
        return;

    let ctl = document.getElementById("error");
    if (ctl != null) {
        ctl.innerHTML="";    
    }
    SendBodyRequest(BuildResetRequestModel(gridId),gridId);
}

function BuildResetRequestModel(gridId) {

    let model = {
    "GridName":gridId,
    "ItemType":0,
    "Items": []
    };
    return model;
}


function BuildRefreshRequestModel(gridId, filters, paginatorObj) {

    let fLen = filters.length;
    let fArray = [];
    for (let i = 0; i < fLen; i++) {
        let filterModel = CreateFilterModel(filters[i]);
        if (filterModel != null) {
            fArray.push(filterModel);
        }
    }

    let paginator = CreatePaginatorModel(paginatorObj);

    let relFilters = getRelFilters(gridId);

    if (relFilters != "")
        relatedFilterObj = jQuery.parseJSON(relFilters)
    else 
        relatedFilterObj = ""

    //get sorting
    let modelSortValue = "";
    let modelSortDir = "";
    let sortItems = jQuery("#"+gridId).find("[data-type='sortOrder']");
    if (sortItems != null) {
        let len = sortItems.length;
        for (let i = 0; i < len; i++) {
            let sortDir = sortItems[i].getAttribute("data-sort-dir");
            if (sortDir != null && sortDir != "none") {
                modelSortDir = sortDir;
                modelSortValue = sortItems[i].getAttribute("data-sort");
                break;
            }
        }
    }

    let model = {
    "GridName":gridId,
    "ItemType":0,
    "Items": fArray,
    "Paginator": paginator,
    "Sort": modelSortValue,
    "SortDirection": modelSortDir,
    "RelatedGridsFilters": relatedFilterObj
    };
    return model;
}

function CreatePaginatorModel(fJQObject) {
    if (fJQObject == null) {
        return null;
    }
    let currentPage = fJQObject.getAttribute("data-current-page");
    let itemsPerPage = fJQObject.value;
    return { "ItemType": 7, "CurrentItmsPerPageValue": itemsPerPage, "CurrentPageIndex": currentPage };
}

function ClearFilter(fJQObject){
    if (fJQObject == null) {
        return;
    }

    let fType = fJQObject.getAttribute("data-filter-type");
    switch (fType) {
        case "enSingleTextFilter":
            fJQObject.value="";
            break;
        case "enSingleDateFilter":
            fJQObject.value="";
            break;
        case "enMultipleTextsFilter":
            let filter = new vanillaSelectBox("#" + fJQObject.id, {"disableSelectAll": true, "search": false, "translations": { "all": "All", "items": "items","selectAll":"All","clearAll":"All"}});
            MultTextFilterRemoveSelection(fJQObject);
            filter.empty();
            break;
        case "enNoFilter":
            return false;
        case "enBooleanFilter":
            fJQObject.checked = false;
            break;
        //default:
        //    return;
    }
    return false;
}

function MultTextFilterSetEvent(selectObj) {
    if (selectObj != null) {
        for (let i = 0; i < selectObj.options.length; i++) {
            selectObj.options[i].click = "alert('change event '+ selectObj.id);";
        }
    }
}

function MultTextFilterRemoveSelection(selectObj) {
    if (selectObj != null) {
        for (let i = 0; i < selectObj.options.length; i++) {
            selectObj.options[i].selected = false;                
        }
    }
}

function CreateFilterModel(fJQObject){
    if (fJQObject == null) {
        return null;
    }

    let fType = fJQObject.getAttribute("data-filter-type");
    switch (fType) {
        case "enSingleTextFilter":
            return CreateSingleTextFilter(fJQObject);
        case "enSingleDateFilter":
            return CreateSingleDateFilter(fJQObject);
        case "enMultipleTextsFilter":
            return CreateMultipleTextFilter(fJQObject);
        case "enBooleanFilter":
            return CreateBooleanFilter(fJQObject);
        case "enNoFilter":
            return null;
        default:
            return null;
    }
}

function CreateSingleTextFilter(fJQObject) {
    let dataSearch = fJQObject.getAttribute("data-search");
    let filterValue =  fJQObject.value;
    if (filterValue != null && filterValue != "") {
        return { "ItemType": 1, "FilterName": encodeURIComponent(dataSearch), "IsSingleItem": true, "Filter": encodeURIComponent(filterValue) };
    }
    else {
        return null;
    }
}

function CreateSingleDateFilter(fJQObject) {
    let dataSearch = fJQObject.getAttribute("data-search");
    let filterValue = fJQObject.value;
    if (filterValue != null && filterValue != "") {
        return { "ItemType": 5, "FilterName": encodeURIComponent(dataSearch), "IsSingleItem": true, "Filter": encodeURIComponent(filterValue) };
    }
    else {
        return null;
    }
}

function CreateMultipleTextFilter(fJQObject) {
    let dataSearch = fJQObject.getAttribute("data-search");
    let filterValue = GetSelectedValues(fJQObject); 
    if (filterValue != null && filterValue != "") {
        return { "ItemType": 3, "FilterName": encodeURIComponent(dataSearch), "IsSingleItem": false, "Filter": filterValue };
    }
    else {
        return null;
    }
}

function CreateBooleanFilter(fJQObject) {
    let dataSearch = fJQObject.getAttribute("data-search");
    let filterValue = fJQObject.checked;
    if (filterValue == true) {
        return { "ItemType": 8, "FilterName": encodeURIComponent(dataSearch), "IsSelected": true};
    }
    else {
        return null;
    }
}
function SendRequest(model, gridId) {

    let modelStr = JSON.stringify(model);
    //alert(modelStr);
    
    let url = getBaseUrl(gridId);
    
    jQuery.post(url, {jsonModel: modelStr}, function(result){
        jQuery("#"+gridId).html(result);
    });


}

function SendBodyRequest(model, gridId) {

    let modelStr = JSON.stringify(model);
    //alert(modelStr);

    //reload the body of the table    
    let url = getTableBodyUrl(gridId); // + "?jsonModel=" + modelStr;
    let bodyId = getTableBodyId(gridId);
    jQuery.post(url, {jsonModel: modelStr}, function(result){
        jQuery("#"+bodyId).html(result);
  });


    //reload the paginators
    url = getPaginatorUrl(gridId);
    let findStr = "[name='" + getPaginatorsName(gridId) + "']";
    jQuery.post(url, {jsonModel: modelStr}, function(result){
        jQuery("#"+gridId).find(findStr).html(result);
  });


}

function SetPartialRefreshFlag(id, flag) {
    let ctl = document.getElementById(id+"_partReset");
    if (ctl == null) {
        return;
    }
    ctl.value == flag;
}

function IsPartialRefresh(id) {
    let ctl = document.getElementById(id+"_partReset");
    if (ctl == null) {
        return false;
    }
    return ctl.value == "true";
}

/************ Tab ****************/

/******** Pagination & Sorting *********/
function getAPaginatorObj(gridId) {
    let paginators = jQuery("#"+gridId).find("[data-type='paginator']");
    let paginator = null;
    if (paginators != null) {
        paginator = paginators[0];
    }
    return paginator;
}

function SetPaginatorsAttribute(gridId, attribute, value) {
    let paginators = jQuery("#"+gridId).find("[data-type='paginator']");
    if (paginators != null) {
        let len = paginators.length;
        for (let i = 0; i < len; i++) {
            paginators[i].setAttribute(attribute,value);
        }
    }
}

function nextPage(obj) {
    if (obj == null)
        return;
    let gridId = obj.getAttribute("data-grid-id");
    let paginator = getAPaginatorObj(gridId);
    if (paginator != null) {
        let pageIndex = Number(paginator.getAttribute("data-current-page"));
        pageIndex++;
        paginator.setAttribute("data-current-page",pageIndex);
        RefreshGrid(paginator, true, false);
    }
}

function prevPage(obj) {
    if (obj == null)
        return;
    let gridId = obj.getAttribute("data-grid-id");
    let paginator = getAPaginatorObj(gridId);
    if (paginator != null) {
        let pageIndex = Number(paginator.getAttribute("data-current-page"));
        pageIndex--;
        if (pageIndex > 0) {
            paginator.setAttribute("data-current-page",pageIndex);
            RefreshGrid(paginator, true, false);
        }
    }
}

function SetInitSort(gridId) {
    jQuery("#"+gridId).find("[img-sort-type='asc']").addClass("grid-hidden");
    jQuery("#"+gridId).find("[img-sort-type='desc']").addClass("grid-hidden");
}

function SetSort(obj) {
    if (obj == null)
        return;

    let gridId = obj.getAttribute("data-grid-id");
    let selItemSortDir = obj.getAttribute("data-sort-dir");

    //remove all previous sorting
    let sortItems = jQuery("#"+gridId).find("[data-type='sortOrder']");
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

    let newSortDir = "asc";
    //if current column was already sorted desc, then switch with asc
    if (selItemSortDir == 'asc') {
        newSortDir = "desc";
        jQuery(obj).find("[img-sort-type=desc]").removeClass("grid-hidden");
        jQuery(obj).find("[img-sort-type=none]").addClass("grid-hidden");
    }
    else {
        jQuery(obj).find("[img-sort-type=asc]").removeClass("grid-hidden");
        jQuery(obj).find("[img-sort-type=none]").addClass("grid-hidden");
    }
    obj.setAttribute("data-sort-dir", newSortDir);

    RefreshGrid(obj, true);
}

/********************************/
/********* Common *************/
/********************************/

/********** Startup code ********/

function getBaseUrl(id) {

    let ctl = document.getElementById(id+"_pBackUrl");
    if (ctl == null) {
        return "";
    }
    return ctl.value;
}

function getTableBodyUrl(id) {
    let ctl = document.getElementById(id+"_pBackUrlBody");
    if (ctl == null) {
        return "";
    }
    return ctl.value;
}

function getPaginatorUrl(id) {
    let ctl = document.getElementById(id+"_pBackUrlPaginator");
    if (ctl == null) {
        return "";
    }
    return ctl.value;
}

function getTableBodyId(id) {
    return id + "-tblBody";
}

function getPaginatorsName(id) {
    return id + "_paginator";
}

function getRelFilters(id) {    
    let ctl = document.getElementById(id+"_relFilters");
    if (ctl == null) {
        return "";
    }
    return ctl.value;
}

function containsValue(selectObj, valueToCheck) {
    for (let i = 0; i < selectObj.options.length; i++) {
        if (selectObj.options[i].text == valueToCheck) {
            return true;
        }
    }
    return false;
}

function setSelectedValue(selectObj, valueToSet) {
    //reset the selection
    if (selectObj.options.length > 0)
        selectObj.options[0].selected = true;

    for (let i = 0; i < selectObj.options.length; i++) {
        if (selectObj.options[i].text == valueToSet) {
            selectObj.options[i].selected = true;
            return;
        }
    }
}

function getSelectedValue(controlName) {
    let ctl = document.getElementById(controlName);
    if (ctl == null) {
        return "";
    }
    return ctl.value;
}

function GetSelectedValues(selectObj) {
    if (selectObj == null) {
        return [];
    }
    let arr = [];
    for (let i = 0; i < selectObj.options.length; i++) {
        if (selectObj.options[i].selected) {
            arr.push(encodeURIComponent(selectObj.options[i].value));
        }
    }
    return arr;
}
