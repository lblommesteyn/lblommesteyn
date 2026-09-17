jQuery(document).ready(function () {
    hideSideBarsIfNeeded();
});

/* Back to top function on page */
jQuery(function () {
    jQuery.scrollUp({
        scrollName: 'scrollUp',
        topDistance: '300',
        topSpeed: 300,
        animation: 'fade',
        animationInSpeed: 200,
        animationOutSpeed: 200,
        scrollText: '',
        activeOverlay: false
    });
});

function offset(el) {
	if (el != null) {
		var rect = el.getBoundingClientRect(),
			scrollLeft = window.pageXOffset || document.documentElement.scrollLeft,
			scrollTop = window.pageYOffset || document.documentElement.scrollTop;
		return { top: rect.top + scrollTop, left: rect.left + scrollLeft }
	}
	else {
		return null;
	}
	
}

function hideSideBarsIfNeeded() {
    var leftCollapseFlag = false, rightCollapseFlag = false;
    //left section
    var leftSections = document.getElementsByClassName("left-rail");
    if (leftSections.hasChildNodes === false) {
        leftSections[0].classList.add("left-rail-hidden");
        leftSections[0].classList.remove("left-rail");
        leftCollapseFlag = true;
    }
    else if (isEmptyBar(leftSections[0])) {
        leftSections[0].classList.add("left-rail-hidden");
        leftSections[0].classList.remove("left-rail");
        leftCollapseFlag = true;
    }

    //right section
    var rightSections = document.getElementsByClassName("right-rail");
    if (rightSections.length == 0) {
        rightCollapseFlag = true;
    }

    //expand the main content section if needed
    var mainSection = document.getElementsByClassName("main")[0];
    if (leftCollapseFlag && rightCollapseFlag) {
        var element1 = document.getElementsByClassName("main")[0];
        element1.classList.add("main-right-expand-full");
        element1.classList.remove("main");
        mainSection = element1;
    }
    else if (leftCollapseFlag) {
        var element2 = document.getElementsByClassName("main")[0];
        element2.classList.add("main-right-expand-to-left");
        element2.classList.remove("main");
        mainSection = element2;
    }
    else if (rightCollapseFlag) {
        var element3 = document.getElementsByClassName("main")[0];
        element3.classList.add("main-right-expand-to-right");
        element3.classList.remove("main");
        mainSection = element3;
    }

    //adjustHeight(leftSections, rightSections, mainSection);
    adjustWidth(leftSections, rightSections, mainSection);
}

function adjustHeight(leftRail, rightRail, mainContent) {
    if (mainContent == null) return;
    if (leftRail != null) {
        jQuery(leftRail).height(jQuery(mainContent).height());
    }
    if (rightRail != null) {
        jQuery(rightRail).height(jQuery(mainContent).height());
    }
}

function isMobile() {
    if (navigator.userAgent.match(/iPhone|iPad|iPod/i)) return true;
    if (navigator.userAgent.match(/Android/i)) return true;
    if (navigator.userAgent.match(/BlackBerry/i)) return true;
    return false;

}

function adjustWidth(leftRail, rightRail, mainContent) {
	if (HTMLCollection.prototype.isPrototypeOf(leftRail)) {
		leftRail = leftRail[0];
	}
	
    if (isMobile()) {
        if (leftRail != null && leftRail.length != 0) {
            if (screen.width <= 1024 && screen.height <= 1024) return;
            jQuery(mainContent).css("margin-left", "20px");
        }
    }
    if (screen.width <= 1024) return;


    if (mainContent == null) return;

    var isleft = false;
    var isright = false;

    var off = offset(leftRail);
	
	
	

    if (leftRail != null && leftRail.length != 0) {
        jQuery(mainContent).css("margin-left", "10px");

        var leftWidth = jQuery(leftRail).width();
		var margin = jQuery(jQuery("#phMainContent")[0]).css("margin-left")
		margin = parseFloat(margin.match(/\d+/)[0]);
        var mainWidth = jQuery(mainContent).width()  - 35;
        if (leftWidth != null) {
			leftCalculation = leftWidth + margin + 25;
			var calculation = "calc(100% - " + leftCalculation + "px)";
			jQuery(mainContent).css("width", calculation);
			isleft = true;
        }


        refreshLine();

    }

    if (msieversion() !== 0) {
        if (isleft && isright)
            jQuery(mainContent).width("50%");
        else if (isleft || isright)
            jQuery(mainContent).width("75%");
    }
}

window.addEventListener('resize', function (event) {
    refreshLine();

    if (window.innerWidth > 1200) {
        var leftRail = document.getElementsByClassName("left-rail")[0];
        var mainContent = document.getElementsByClassName("main")[0];
        var rightRail = null;
        adjustWidth(leftRail, rightRail, mainContent)
    }

}, true);

function offset(el) {
	if (el != null) {
		var rect = el.getBoundingClientRect(),
			scrollLeft = window.pageXOffset || document.documentElement.scrollLeft,
			scrollTop = window.pageYOffset || document.documentElement.scrollTop;
		return { top: rect.top + scrollTop, left: rect.left + scrollLeft }
	}
	else {
		return null;
	}
	
}

function refreshLine() {
    var leftRail = document.getElementsByClassName("left-rail")[0];
    var mainContent = document.getElementsByClassName("main")[0];

    var leftWidth = jQuery(leftRail).width();

    var mainWidth = jQuery(mainContent).width();

    var margin = 35;

    var calculatedWidth = mainWidth + leftWidth + margin + 6;

    var root = document.querySelector(':root');

    var mainLeftNavigation = jQuery(leftRail).children("div#section-nav")[0];

    var offsetLeft = offset(mainLeftNavigation);
	
	if (offsetLeft == null) {
		return;
	}

    var leftStart = offsetLeft.left;
    var topStart = offsetLeft.top;
	
	var iPadCalc = window.innerWidth - jQuery(leftRail).width() - 120;

    //var mainWidth = jQuery('#phMainContent').width();

    if (leftRail != null) {
        root.style.setProperty('--wrapper-width', calculatedWidth + 'px');
        root.style.setProperty("--wrapper-left", leftStart + 'px');
        root.style.setProperty("--wrapper-top", topStart + 'px');
		root.style.setProperty('--main-content-calculation', iPadCalc + 'px');

    }
    if (jQuery("#breadcrumbs").position().top > 500) {
        root.style.setProperty('--wrapper-width', '0px');
        root.style.setProperty("--wrapper-left", leftStart + 'px');
    }
}

function isEmptyBar(barControl) {
    var nonEmptyChildFlag = false;
    function isNonEmptyChild(value) {
        //The nodeType property returns the node type, as a number, of the specified node.
        //1 - element node, 2 - attribute node, 3 - text node, 8 - comment node
        if (value.nodeType != 8) {
            if (value.nodeType == 3 && value.nodeValue.trim().length > 0 ||
                value.nodeType == 1 && value.childNodes.length > 0) {
                nonEmptyChildFlag = true;
            }
        }
    }

    //special code for IE support
    if (typeof NodeList.prototype.forEach !== "function" && typeof Array.prototype.forEach === "function")
        NodeList.prototype.forEach = Array.prototype.forEach;

    var childNodes = barControl.childNodes;
    childNodes.forEach(isNonEmptyChild);
    return !nonEmptyChildFlag;

}

function msieversion() {
    var ua = window.navigator.userAgent;
    var msie = ua.indexOf("MSIE ");

    if (msie > 0) // If Internet Explorer, return version number
        return parseInt(ua.substring(msie + 5, ua.indexOf(".", msie)));
    else if (window.navigator.userAgent.match(/Trident\/7\./))
        return 11;
    else // If another browser, return 0
        return 0;

}

/************ Tab ****************/
function openCustomTab(evt, tabName) {
  // Declare all variables
  var i, tabcontent, tablinks;

  var parent = document.getElementById(tabName).parentElement;
  //parent.getElementById("demo").innerHTML = x.id;


  // Get all elements with class="tabcontent" and hide them
  tabcontent = parent.getElementsByClassName("tab-content-box");
  for (i = 0; i < tabcontent.length; i++) {
    tabcontent[i].style.display = "none";

  }

  // Get all elements with class="tablinks" and remove the class "active"
  tablinks = parent.getElementsByTagName("li");
  for (i = 0; i < tablinks.length; i++) {
    tablinks[i].className = tablinks[i].className.replace("active", "");
  }

  // Show the current tab, and add an "active" class to the button that opened the tab
  let tabObj = document.getElementById(tabName);
  //tabObj = document.getElementById(tabName).getElementsByClassName("content-box")[0];

  tabObj.style.display = "block";
  evt.currentTarget.className += "active";

}