jQuery(document).ready(function () {
    var deviceType = "";
    checkDeviceType();

});


function checkDeviceType() {
    jQuery.ajax({
        url: '/AjaxService/devicetype.asmx/GetDeviceType',
        type: 'POST',
        contentType: 'application/json; charset=utf-8',
        dataType: 'json',
        success: function (data) {
            console.log(data.d);
            deviceType = JSON.parse(data.d);
            if (deviceType == 'phone') {
                makePhoneClickable();
            }
        }
    });
}

function makePhoneClickable() {
    jQuery('.telephone').each(function () {
        var phonetxt = jQuery(this).text();
        var hreftxt = "tel:+1" + phonetxt.replace("(", "").replace(")", "").replace(" ", "").replace("-", "");
        var htmltxt = "<a href='" + hreftxt + "'>" + phonetxt + "</a>";
        jQuery(this).html("").html(htmltxt);
    });
}