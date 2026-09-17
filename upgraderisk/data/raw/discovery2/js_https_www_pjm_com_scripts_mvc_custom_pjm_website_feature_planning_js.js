
/************* Startup code ********/
jQuery(document).ready(function( $ ){

    let ctl = document.getElementById("hidCostAlloc_isPostBack");
    if (ctl != null) {
        if (ctl.value != "true") {
            ctl.value = true;

            ctl = document.getElementById("projConstExtFilters");
            InitExtFilters(ctl.id);
            let gridId = ctl.getAttribute("grid-id");
            InitFilters(gridId);
            SetInitSort(gridId);
        }
    }
    

});

jQuery(function() {
    jQuery('.cost-alloc-exportToXls').on('click',
    //picks up all the filters settings and sends a post request to generate an Excel file, then downloads it    
    function(event) {
        //Create a search/pagination model
        let obj = event.currentTarget;
        let gridId = obj.getAttribute("data-grid-id");
        let filters = jQuery("#"+gridId).find("[data-type='filter']");
    
        let extFiltersId = obj.getAttribute("ext-filters-id");
        let extFilters = jQuery("#"+extFiltersId).find("[data-type='filter-ext']");
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
            
        let url = "/m/ProjectConst/ProjectConstructionUpgrades";
         
        var request = new XMLHttpRequest();
        request.open('POST', url, true);
        request.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
        request.responseType = 'blob';
            

        request.onload = function() {
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
                link.download = "ProjectConstructionUpgrades.xlsx";

                //document.body.appendChild(link);
                link.click();
                //document.body.removeChild(link);
            }
            else { //any other status
                let errMsg = "Failed to download ProjectConstructionUpgrades.xlsx. Status: " + 
                    request.status + " - " + request.statusText;

                console.error(errMsg);
            }
        };
        request.send('jsonModel='+modelStr);

    });
});

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
    let extFilters = jQuery("#"+containerId).find("[data-type='filter-ext']");
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

function ResetProjConstPostBackFlag() {
    let ctl = document.getElementById("hidCostAlloc_isPostBack");
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

    let filters = jQuery("#"+gridId).find("[data-type='filter']");
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
    
//InitFilters(gridId);


}

//not in use
function DownloadProjConstXL(obj) {
    if (obj == null)
        return;

    //jQuery('#loader').fadeOut('fast');


    let gridId = obj.getAttribute("data-grid-id");
    //console.log("gridId="+ gridId);
    //let filters = $("#"+gridId).find(".filter");
    let filters = jQuery("#"+gridId).find("[data-type='filter']");
    
    
    let extFilters = jQuery("#"+gridId).find("[data-type='filter-ext']");
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
    let ctl = document.getElementById("hidCostAlloc_infoUpgradeId");
    let description = ctl.value;
    OpenModalInfo(description, container);
 }

function OpenCostAllocationInfo(container) {
    let ctl = document.getElementById("hidCostAlloc_CostAllocation");
    let description = ctl.value;
    OpenModalInfo(description, container);
 }

function OpenRequiredDateInfo(container) {
    let ctl = document.getElementById("hidCostAlloc_RequiredDate");
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

function OpenUpgradeDetails(id, container) {

    let ctl = document.getElementById("upgradeDetails");
    //let ctlContent = document.getElementById("upgradeDetailsContent");
    let successFlag = true;
    let url = "/m/ProjectConst/UpgradeDetails" + "?upgradeId=" + id;
    (jQuery(ctl)).load(url, function (response, status, xhr) {
        if (status != "success") {
            //enable next row for debugging
            //jQuery("#error").html(response);
            let errMsg = "Failed to open project details (upgradeId=" + id + "): " + xhr.status + " - " + xhr.statusText;
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

function CloseUpgradeDetails() {
    //cleanup
    let ctl = document.getElementById("upgradeDetails");
    ctl.style.display = "none";
}

function replaceText(id) {
    OpenUpgradeDetails(id)
}

function OpenCostAllocationDetails(id) {

    let ctl = document.getElementById("costAllocationDetails");
    let url = "/m/ProjectConst/UpgradeCostAllocations" + "?upgradeId=" + id;
    (jQuery(ctl)).load(url, function (response, status, xhr) {
        if (status != "success") {
            //enable next row for debugging
            //jQuery("#error").html(response);
            let errMsg = "Failed to open cost allocations details (upgradeId=" + id + "): " + xhr.status + " - " + xhr.statusText;
            console.error(errMsg);
        }
        else {
            jQuery("#costAllocationDetails").css('display', 'block');
        }
    });
}

//function OpenCostAllocationDetails(id, values) {

//    //converted to jQuery
//    jQuery("#costAllocUpgrId").html(id);
//    jQuery("#costAllocationDetails").css('display', 'block');

//    //List out all Cost Allocation Percents in the modal.
//    if (values) {
//        let costAllocationPercentList = values.split(",");
//        for (var costAllocationPercentItem of costAllocationPercentList) {
//            var costAllocationPercentSubstringsList = costAllocationPercentItem.split(/(:)/);
//            //create individual spans of cost allocation percent items wrapped around a div.
//            //set title and value to each span i.e. Title =  AEC: & Value = 3.99
//            var costAllocationPercentOuterDiv = jQuery('<div/>', {
//                class: 'costAllocationPercentItem'
//            }).appendTo("#costAllocDetailsBodyId");
//            jQuery('<span/>', {
//                html: (costAllocationPercentSubstringsList[0] + costAllocationPercentSubstringsList[1]).bold()
//            }).appendTo(costAllocationPercentOuterDiv);
//            jQuery('<span/>', {
//                html: costAllocationPercentSubstringsList[2]
//            }).appendTo(costAllocationPercentOuterDiv);
//        }
//    }
//}
function CloseCostAllocationDetails() {
    //cleanup
    jQuery("#costAllocationDetails").css('display', 'none');
    //jQuery('#costAllocDetailsBodyId').html('');
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

function OpenToolTipInfo(description, container) {
    jQuery('#modalInfo').css('display', 'block');
    jQuery('#infoDescriptionId').html(description);
    let rect = container.getBoundingClientRect();
    let x = rect.left + rect.width + window.scrollX;
    let y = rect.top + + window.scrollY; // + rect.height + 5 + window.scrollY;
    //console.log('x='+rect.x + ', y=' +rect.y);
    infoModalMouseEnterAction('#modalInfo', x, y);
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
