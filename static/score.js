var display, doc, download, offset, scoredata, section, category, logo, dateString;

/**
appends text to the pdf object

indent - text indent from the left
topOffset - vertical offset before text
bottomOffset - vertical offset after text
text - text to add to document
*/
function appendText(indent, topOffset, bottomOffset, text) {
	offset += topOffset;
	if (offset >= 280) {
		doc.addPage();
		offset = 30;
	}
	var lines = doc.splitTextToSize(text, 72 * (170 - indent) / 25.6);
	doc.text(indent, offset, lines[0]);
	if (lines.length > 1) {
	for (a = 1; a < lines.length; a++) {
		offset += 6;
		doc.text(indent + 10, offset, lines[a]);
	}}
	offset += bottomOffset;
}

/**
adds a statistic to the pdf object

statName - the name of the stat, ex: "open questions"
statValue - the value of the stat, ex: "3"
*/
function addStat(statName, statValue) {
	appendText(25, 0, 8, statName);
	doc.text(120 - (statValue.length * 2.56), offset - 8, statValue);
}

/**
converts a formatted chatscript log string into a javascript object

string - formatted chatscript log string

returns a javascript object
*/
function fixJSON(string) {
// starts by replacing text used to escape {} and []
	var output = replaceAll("/openSquare/", "[", string);
	output = replaceAll("/closeSquare/", "]", output);
	output = replaceAll("/openCurly/", "{", output);
	output = replaceAll("/closeCurly/", "}", output);
// since sometimes a subject or category name has quotes around it, some subjects
// and categories might have 2 pairs of quotes on each side, so this fixes that
	output = replaceAll("\"\"", "\"", output);
// removes any new lines and invalid characters
	output = replaceAll("\n", "", output);
	output = replaceAll("\0", "", output);
	return JSON.parse(output.trim());
}

/**
replaces all instances of a string with a different string

find - the string that will be replaced
replace - the string that will replace the find string
str - the string that will be searched through

returns the changed string

ex:
replaceAll("a", "b", "a bad string a") == "b bbd string b"
*/
function replaceAll(find, replace, str) {
  return str.replace(new RegExp(find, 'g'), replace);
}

/**
returns the html text to display the score data
*/
function generateHTML() {
	var content = "<div style=\"border: 5px solid blue\">" //\"white-space:nowrap\">"
	//+ "overflow-y:scroll;\""
	+ "<p>Scorecard for " + scoredata.name + "</p>";
	for (i = 0; i < scoredata.sections.length; i++) {
		section = scoredata.sections[i];
		content += "<h2><strong style=\"margin-left:10px\">"
		 	+ section.name + "</strong></h2>";
		for (j = 0; j < section.categories.length; j++) {
			category = section.categories[j];
			content += "<strong style=\"margin-left:20px\">"
				 + category.name + "</strong>";
			content += "<p style=\"margin-left:40px\">";
			if (category.questions.length == 0) {
				content += "No question asked.<br>";
			}
			for (k = 0; k < category.questions.length; k++) {
				content += category.questions[k] + "<br>";
			}
			content += "</p>";
		}
	content += "<p style=\"margin-left:20px\">" +  
	section.summary + "</p><br><br>";
	}
	content += "<p style=\"margin-left:20px\">"
		+ "<b>Total questions asked:  " 
	        + scoredata["total questions"]
                + "</b></p>";
//		+ "<br>Open Questions:  " + scoredata["open questions"]
//		+ "<br>Open Question Percent: "
//	 	+ scoredata["open question percent"]
//		+ "<br>Open in first 5:  "
//		+ scoredata["open in first 5"]
//		+ "<br>Open in first 10:  "
//		+ scoredata["open in first 10"]
//		+ "<br>Open in first 15:  "
//		+ scoredata["open in first 15"]
//		+ "<br>Closed questions:  "
//		+ scoredata["closed questions"]
//		+ "<br>Closed Question Percent:  "
//		+ scoredata["closed question percent"]
//		+ "<br>Open/Closed Ratio:  "
//		+ scoredata["open/closed ratio"]
//		+ "<br><br>Summarizing Questions:</b></p>"
//		+ "<div style=\"margin-left:40px\">"
//	for (i = 0; i < scoredata["summarizing questions"].length; i++) {
//		content += scoredata["summarizing questions"][i] + "<br>";
    //	}
//      content += "</div>";
	content += "<strong style=\"margin-left:20px\">"
		+ "All Questions Asked:</strong>"
	        + "<div style=\"margin-left:40px\">";
	for (i = 0; i < scoredata.transcript.length; i++) {
		content += scoredata.transcript[i] + "<br>";
	}
	content += "</div></div>";
	return content;
}

/**
sets the value of doc to a pdf that properly displays the score data
*/
function generatePDF() {
	
// images must be converted to a data uri in order to be placed in pdf
	logo = "data:image/jpeg;base64,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"
	
//  HERE IS WHERE YOU ADJUST THE FONT/ TEXT ATTRIBUTES
	
	doc = new jsPDF();
	doc.setFontSize(10); // DEFAULT FONT SIZE IS 18
	doc.setFontType("bold"); // DEFAULT IS BOLD
	offset = 30;
	appendText(50, 0, 14, "Feedback Summary for " + scoredata.name + " from " + dateString)
	doc.addImage(logo, 'JPEG', 15, 20, 30, 15);
	
	for (i = 0; i < scoredata.sections.length; i++) {

		section = scoredata.sections[i];
		doc.setFontSize(10);
		doc.setFontType("bold");
		appendText(20, 3, 7, section.name);
		
		for (j = 0; j < section.categories.length; j++) {
			doc.setFontSize(8);
			doc.setFontType("bold");
			category = section.categories[j];
			appendText(30, 2, 7, category.name);
			doc.setFontType("normal");

			if (category.questions.length == 0) {
				appendText(40, 0, 6, "No question asked.");
			}
			for (k = 0; k < category.questions.length; k++) {
				appendText(40, 0, 6, category.questions[k]);
			}
		}
	doc.setFontType("italic");
	doc.setFontSize(8);
	appendText(25, 3, 8, section.summary)
	}
	doc.setFontType("italic");
	doc.setFontSize(8);
	offset += 3;
	addStat("Total questions asked:", scoredata["total questions"]);
	//addStat("Open Questions:", scoredata["open questions"]);
	//addStat("Open Question Percent:", scoredata["open question percent"]);
	//addStat("Open in first 5:", scoredata["open in first 5"]);
	//addStat("Open in first 10:", scoredata["open in first 10"]);
	//addStat("Open in first 15:", scoredata["open in first 15"]);
	//addStat("Closed questions:", scoredata["closed questions"]);
	//addStat("Closed Question Percent:", scoredata["closed question percent"]);
	//addStat("Open/Closed Ratio:", scoredata["open/closed ratio"]);
	//appendText(25, 2, 8, "Summarizing Questions:");
	//doc.setFontType("normal");
	//doc.setFontSize(8);
	//for (i = 0; i < scoredata["summarizing questions"].length; i++) {
		//appendText(35, 0, 7, scoredata["summarizing questions"][i]);
	//}
	doc.setFontType("italic");
	doc.setFontSize(8);
	appendText(25, 5, 9, "All Questions Asked:");
	doc.setFontType("normal");
	doc.setFontSize(8);
	for (i = 0; i < scoredata.transcript.length; i++) {
		appendText(35, 0, 7, scoredata.transcript[i]);
	}
}

/**
sets the value of dateString based on the current date and time

format example:

5/4/14 4:02 pm
8/13/15 11:34 am
*/

function getDate() {
	var time = new Date();
	var month = time.getMonth() + 1;
	var day = time.getDate();
	var year = time.getFullYear() % 100;
	var hour = time.getHours() % 12;
	var ampm;
	if (time.getHours() < 12) {ampm = "am"}
	else {ampm = "pm"}
	if (hour == 0) {hour = 12;}
	var minute = time.getMinutes();
	if (minute < 10) {minute = "0" + minute}
	dateString = month + "/" + day + "/" + year + " " + hour + ":" + minute + " " + ampm;
}


/**
function called by webplayer when scoring
*/
var score = function score(scorejson) {

	scoredata = fixJSON(scorejson);
	getDate();
	
//	generatePDF();
//    var pdfdata = doc.output('datauristring'); 	
	display = document.createElement("div");
	display.style.textAlign = "left"; 
//   	display.data = pdfdata;
	display.innerHTML = generateHTML();
	display.height = "95%";
	display.width = "100%";

/*    var link = document.createElement("a");
    link.download = "Summary";
    link.href = pdfdata;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    delete link;
*/
//    document.location.href = pdfdata;
//    var iframe = "<iframe width='100%' height='100%' src='https://docs.google.com/gview?url=" + pdfdata + "&embedded=true'></iframe>"
    
//    document.body.innerHTML = iframe;
/*	download = document.createElement("input");
	download.type = "button";
	download.value = "Open Score .pdf";
        download.onclick = function() {
	    var x = window.open();
            x.document.open();
            x.document.write(iframe);
            x.document.close();
	}
	var expertAnswers = document.createElement("input");
	expertAnswers.type = "button";
	expertAnswers.value = "Download Expert Answers";
	expertAnswers.onclick = function() {
		window.open("http://128.146.170.201/Downloads/ExpertAnswers.pdf");
	}
*/
	var placement = document.getElementById("scoreholder");
	if (placement == null) { placement = document.body;} 
//	placement.appendChild(download);
//	placement.appendChild(expertAnswers);
	placement.appendChild(display);
}

/* var getUrlParameter = function getUrlParameter(sParam) {
    var sPageURL = decodeURIComponent(window.location.search.substring(1)),
        sURLVariables = sPageURL.split('&'),
        sParameterName,
        i;
    
    for (i = 0; i < sURLVariables.length; i++) {
	sParameterName = sURLVariables[i].split('=');
	
	if (sParameterName[0] === sParam) {
	    return sParameterName[1] === undefined ? true : sParameterName[1];
	}
    }
};


the scoredata object should have the following fields:
	scoredata.name 	(a string)
	scoredata["total questions"] 	(a string)
	scoredata["open questions"] 	(a string)
	scoredata["open question percent"]   (a string)
	scoredata["open in first 5"] 	(a string)
	scoredata["open in first 10"] 	(a string)
	scoredata["open in first 15"] 	(a string)
	scoredata["closed questions"] 	(a string)
	scoredata["closed question percent"] 	(a string)
	scoredata["open/closed ratio"] 	(a string)
	scoredata["summarizing questions"] 	(an array of strings)
	scoredata.transcript 	(an array of strings) 
	scoredata.sections 	(an array of objects)
	scoredata.sections[n].name 	(a string)
	scoredata.sections[n].summary 	(a string)
	scoredata.sections[n].categories   (an array of objects)
	scoredata.sections[n].categories[k].name     ( a string)
	scoredata.sections[n].categories[k].questions 	(an array of strings)

	
*/
