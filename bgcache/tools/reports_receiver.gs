/**
 * bgcache problem reports -> a Google Drive folder (Google Apps Script).
 *
 * Help > Report a problem > Send posts {name, version, zip (base64)} here,
 * and this files the zip in your Drive folder. Set up once:
 *
 *  1. In Google Drive, make a folder for reports. Open it: the long code at
 *     the end of its address is the folder id. Put it in FOLDER_ID below.
 *  2. Go to script.google.com > New project, paste this file in, Save.
 *  3. Deploy > New deployment > type "Web app":
 *       Execute as: Me;  Who has access: Anyone.
 *     Deploy, allow access, and copy the Web app URL.
 *  4. Put that URL in the pipeline profile as "reports_url".
 *     Empty "reports_url" (the default): no Send button, Save report only.
 *
 * Only zips under MAX_BYTES are accepted. Anyone with the URL can send a
 * report, so keep it in your profile rather than posting it publicly.
 */
var FOLDER_ID = "PUT_YOUR_FOLDER_ID_HERE";
var MAX_BYTES = 20 * 1024 * 1024;

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    var bytes = Utilities.base64Decode(body.zip || "");
    if (!bytes.length || bytes.length > MAX_BYTES) {
      return answer({ok: false, error: "empty or too big"});
    }
    var name = String(body.name || "bgcache_report.zip").replace(/[^A-Za-z0-9_.-]/g, "_");
    if (!/\.zip$/.test(name)) name += ".zip";
    var blob = Utilities.newBlob(bytes, "application/zip", name);
    var file = DriveApp.getFolderById(FOLDER_ID).createFile(blob);
    file.setDescription("bgcache " + String(body.version || "?"));
    return answer({ok: true, id: file.getId()});
  } catch (error) {
    return answer({ok: false, error: String(error)});
  }
}

function answer(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
      .setMimeType(ContentService.MimeType.JSON);
}
