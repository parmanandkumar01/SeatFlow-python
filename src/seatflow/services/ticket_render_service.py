"""Electronic Reservation Slip (ERS) ticket rendering service.

Ports the original ticket-template.html into a clean-room Python
rendering service. Accepts a booking DTO (dict) matching the IRCTC
ERS response structure and produces HTML suitable for display in
QWebEngineView or export to PDF via QWebEnginePage.printToPdf().

Template placeholders from ticket-template.html:
  {HtmlTitle}, {r.bookingResponseDTO.*}, {FullClassName},
  {PassengerRowsPlaceholder}, {r.transactionId}, {qrbase64String}

All rendering is local and offline — no network I/O.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# ERS HTML template (port of ticket-template.html)
# Angular-style placeholders are substituted at render time.
# ---------------------------------------------------------------------------

_ERS_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{HtmlTitle}</title>
</head>
<body>
    <div id="print-section" oncontextmenu="return false" unselectable="on"
    onselectstart="return false;" onmousedown="return false;"
    style="width: 100%; font-family: Calibri;" class="ng-star-inserted">
    <table width="90%" id="printTable" align="center" cellpadding="0" cellspacing="0" border="0"
        style="border: 2px solid #000000; font-family: Calibri;" class="ng-star-inserted">
        <tr><!----></tr>
        <tr>
            <td width="20%" align="right" class="ng-star-inserted"><!----><!----></td>
            <td id="heading" width="60%" align="center"><u><b>
                <span style="font-family: Calibri; font-size: 17px; color: black;"
                class="ng-star-inserted">Electronic Reservation Slip (ERS)</span>
                <span style="font-family: Calibri; font-size: 13px;" class="ng-star-inserted">-Normal User</span></b></u></td>
            <td width="20%" align="left" class="ng-star-inserted"><!----><!----></td>
        </tr>
        <tr>
            <td width="33%" align="left" style="padding-left: 10px;"><img
                    alt="Indian railway logo" width="60" class="ng-star-inserted"
                    src="{railway_logo}"></td>
            <td width="33%" align="right" style="padding-right: 10px;"><img
                    alt="IRCTC Logo" width="60" src="{irctc_logo}"></td>
        </tr>
    </table>
    <table width="100%" align="center">
        <tr>
            <td width="20%" align="left" style="text-align: center;"><span
                    style="font-family: Calibri; font-size: 15px; color: black;"
                    class="ng-star-inserted"><strong>Booked From</strong></span></td>
            <td width="40%" align="center" style="text-align: center;"><span
                    style="font-family: Calibri; font-size: 16px; color: black; font-weight: bold;">{from_stn_name} ({from_stn})</span></td>
            <td width="30%" align="right" style="text-align: center;"><span
                    style="font-family: Calibri; font-size: 16px; color: black;"
                    class="ng-star-inserted">{resvn_upto_stn_name} - {resvn_upto_stn}</span></td>
        </tr>
        <tr>
            <td width="30%" align="left" style="text-align: center;"><span
                    style="font-family: Calibri; font-size: 16px; color: black;"
                    class="ng-star-inserted">Start Date* {journey_date}</span></td>
            <td width="40%" align="center"><span
                    style="font-family: Calibri; font-size: 16px; color: black; font-weight: bold;"
                    class="ng-star-inserted">Departure* {boarding_date}</span></td>
            <td width="30%" align="right" style="text-align: center;"><span
                    style="font-family: Calibri; font-size: 16px; color: black;"
                    class="ng-star-inserted">Arrival* {dest_arrv_date}</span></td>
        </tr>
    </table>
    <tr style="border-bottom: 2px solid #000000; border-top: 2px solid #000000;">
        <td>
            <table width="100%" align="center">
                <tr>
                    <td width="22%" align="center"><span
                            style="font-family: Calibri; font-size: 15px; color: black; text-align: center;"
                            class="ng-star-inserted"><strong>PNR</strong></span></td>
                    <td width="56%" align="center"><span
                            style="font-family: Calibri; font-size: 15px; color: black; text-align: center;"
                            class="ng-star-inserted"><strong>Train No./Name</strong></span></td>
                    <td width="22%" align="center"><span
                            style="font-family: Calibri; font-size: 15px; color: black; text-align: center;"
                            class="ng-star-inserted"><strong>Class</strong></span></td>
                </tr>
                <tr>
                    <td width="22%" align="center"><span
                            style="font-family: Calibri; font-size: 18px; color: rgb(46, 116, 181); text-align: center;"
                            class="ng-star-inserted"><strong>{pnr_number}</strong></span></td>
                    <td width="56%" align="center"><span
                            style="font-family: Calibri; font-size: 18px; color: rgb(46, 116, 181); text-align: center;"
                            class="ng-star-inserted"><strong>{train_number} / {train_name}</strong></span></td>
                    <td width="22%" align="center"><span
                            style="font-family: Calibri; font-size: 18px; color: rgb(46, 116, 181); text-align: center;"
                            class="ng-star-inserted"><strong>{full_class_name} ({journey_class})</strong></span></td>
                </tr>
                <tr>
                    <td width="22%" align="center"><span
                            style="font-family: Calibri; font-size: 15px; color: black; text-align: center;"
                            class="ng-star-inserted"><strong>Quota</strong></span></td>
                    <td width="56%" align="center"><span
                            style="font-family: Calibri; font-size: 15px; color: black; text-align: center;"
                            class="ng-star-inserted"><strong>Distance</strong></span></td>
                    <td width="22%" align="center"><span
                            style="font-family: Calibri; font-size: 15px; color: black; text-align: center;"
                            class="ng-star-inserted"><strong>Booking Date</strong></span></td>
                </tr>
                <tr>
                    <td width="22%" align="center"><span
                            style="font-family: Calibri; font-size: 13px; color: black; text-align: center;">{booked_quota} ({journey_quota})</span></td>
                    <td width="56%" align="center"><span
                            style="font-family: Calibri; font-size: 13px; color: black; text-align: center;"
                            class="ng-star-inserted">{distance} KM </span></td>
                    <td width="22%" align="center"><span
                            style="font-family: Calibri; font-size: 13px; color: black; text-align: center;">{booking_date} HRS</span></td>
                </tr>
            </table>
        </td>
    </tr>
    <tr>
        <td style="padding: 0px 10px;"><span
                style="font-family: Calibri; font-size: 17px; color: black;"
                class="ng-star-inserted"><strong><u>Passenger Details</u></strong></span></td>
    </tr>
    <tr>
        <td>
            <table width="100%" align="left">
                <tr align="center"
                    style="padding-top: 20px; font-family: Calibri; font-size: 14px; color: black; font-weight: bold;"
                    class="ng-star-inserted">
                    <td width="3%"><b>#</b></td>
                    <td width="19%" align="left"><b>Name</b></td>
                    <td width="7%" align="left"><b>Age</b></td>
                    <td width="9%" align="left"><b>Gender</b></td>
                    <td width="25%" align="left">&nbsp;&nbsp;&nbsp;&nbsp;<b>Booking Status</b></td>
                    <td width="25%" align="left">&nbsp;&nbsp;&nbsp;&nbsp;<b>Current Status</b></td>
                </tr>
                {passenger_rows}
            </table>
        </td>
    </tr>
    <tr height="5"></tr>
    <tr width="100%" style="padding: 0px 0px 0px 10px; border-top: 2px solid #000000;">
        <td width="100%">
            <table width="100%">
                <tr>
                    <td width="100%"><span
                            style="font-family: Calibri; font-size: 14px; color: black;"
                            class="ng-star-inserted"><strong>Transaction ID: {transaction_id}</strong></span></td>
                </tr>
                <tr class="ng-star-inserted">
                    <td width="100%" class="ng-star-inserted"><span
                            style="font-family: Calibri; font-size: 14px; color: black;"
                            class="ng-star-inserted">IR recovers only 57% of cost of travel on an average.</span></td>
                </tr>
                <tr>
                    <td width="100%"><span
                            style="font-family: Calibri; font-size: 17px; color: black;"
                            class="ng-star-inserted"><strong><u>Payment Details</u></strong></span></td>
                </tr>
                <td width="100%" align="left">
                    <table width="100%" class="ng-star-inserted">
                        <tr class="ng-star-inserted">
                            <td width="60%"
                                style="font-family: Calibri; font-size: 13px; color: black; margin-left: -2px; position: absolute;"
                                class="ng-star-inserted"> Ticket Fare</td>
                            <td width="40%"
                                style="font-family: Calibri; font-size: 13px; color: black;"
                                class="ng-star-inserted"> \u20b9 {total_fare}</td>
                        </tr>
                        <tr class="ng-star-inserted">
                            <td width="60%"
                                style="font-family: Calibri; font-size: 13px; color: black; margin-left: -2px; position: absolute;"
                                class="ng-star-inserted"> IRCTC Convenience Fee (Incl. of GST)</td>
                            <td width="40%"
                                style="font-family: Calibri; font-size: 13px; color: black;"
                                class="ng-star-inserted"> \u20b9 {service_charge_total}</td>
                        </tr>
                        <tr class="ng-star-inserted">
                            <td width="60%"
                                style="font-family: Calibri; font-size: 13px; color: black; margin-left: -2px; position: absolute;"
                                class="ng-star-inserted"> Total Fare (all inclusive)</td>
                            <td width="40%"
                                style="font-family: Calibri; font-size: 13px; color: black;"
                                class="ng-star-inserted"> \u20b9 {total_collectible_amount}</td>
                        </tr>
                    </table>
                </td>
                <tr height="5"></tr>
                <tr>
                    <td><span style="font-family: Calibri; font-size: 11px; color: black;"
                        class="ng-star-inserted">PG Charges as applicable (Additional)</span></td>
                </tr>
            </table>
            <table width="29%" align="right">
                <tr>
                    <td width="100%" align="right"><img height="150" width="150"
                        style="margin-right: 20px" src="data:image/png;base64,{qrbase64_string}"></td>
                </tr>
            </table>
        </td>
    </tr>
    <tr style="border-bottom: 1px solid black;">
        <td>
            <ul style="list-style-type: none; margin: 0px; padding: 0px 10px;"
                class="ng-star-inserted">
                <li style="font-family: Calibri; font-size: 12px; color: black; text-align: justify; padding-left: 1px;"
                    class="ng-star-inserted"><strong>IRCTC Convenience Fee is charged per e-ticket irrespective of number of passengers on the ticket.</strong></li>
                <li style="font-family: Calibri; font-size: 13px; color: black; padding: 3px 0px;"><strong>* The printed Departure and Arrival Times are liable to change. Please Check correct departure, arrival from Railway Station Enquiry or Dial 139 or SMS RAIL to 139.</strong></li>
            </ul>
        </td>
    </tr>
    <tr>
        <td>
            <ul style="list-style-type: disc !important; padding: 0px 25px; margin-bottom: 5px;"
                class="ng-star-inserted">
                <li style="font-family: Calibri; font-size: 13px; color: black; padding-top: 5px; text-align: justify;"
                    class="ng-star-inserted"> This ticket is booked on a personal User ID, its sale/purchase is an offence u/s 143 of the Railways Act,1989. </li>
                <li style="font-family: Calibri; font-size: 13px; color: black; padding: 0px; text-align: justify;">
                    Prescribed original ID proof is required while travelling along with SMS/ VRM/ ERS otherwise will be treated as without ticket and penalized as per Railway Rules.</li>
            </ul>
        </td>
    </tr>
    <tr class="ng-star-inserted">
        <td width="100%" style="padding-left: 10px;"><span
                style="font-family: Calibri; font-size: 12px; color: black;"
                class="ng-star-inserted"><strong>Indian Railways GST Details:</strong></span></td>
    </tr>
    <tr>
        <td style="padding: 0px 10px;">
            <table align="left" width="80%" class="ng-star-inserted">
                <tr>
                    <td width="25%"><span style="font-family: Calibri; font-size: 12px; color: black;"
                        class="ng-star-inserted">Invoice Number: </span></td>
                    <td width="25%"><span
                        style="font-family: Calibri; font-size: 12px; color: black;">{gst_invoice_number}</span></td>
                    <td width="25%"><span style="font-family: Calibri; font-size: 12px; color: black;"
                        class="ng-star-inserted">Address: </span></td>
                    <td width="25%"><span
                        style="font-family: Calibri; font-size: 12px; color: black;">{gst_supplier_address}</span></td>
                </tr>
            </table>
        </td>
    </tr>
    <tr>
        <td style="padding: 0px 10px;">
            <table align="left" width="80%" class="ng-star-inserted">
                <tr>
                    <td width="25%"><span style="font-family: Calibri; font-size: 12px; color: black;"
                        class="ng-star-inserted">SAC Code: </span></td>
                    <td width="25%"><span
                        style="font-family: Calibri; font-size: 12px; color: black;">{gst_sac_code}</span></td>
                    <td width="25%"><span style="font-family: Calibri; font-size: 12px; color: black;"
                        class="ng-star-inserted">GSTIN: </span></td>
                    <td width="25%"><span
                        style="font-family: Calibri; font-size: 12px; color: black;">{gst_gstin_supplier}</span></td>
                </tr>
            </table>
        </td>
    </tr>
    <tr>
        <td style="padding: 0px 10px;">
            <table align="left" width="80%" border="0" class="ng-star-inserted">
                <tr>
                    <td width="25%"><span style="font-family: Calibri; font-size: 12px; color: black;"
                        class="ng-star-inserted">Taxable Value: </span></td>
                    <td width="25%"><span
                        style="font-family: Calibri; font-size: 12px; color: #000000;"
                        class="ng-star-inserted">{gst_taxable_value}</span></td>
                    <td width="25%"><span style="font-family: Calibri; font-size: 12px; color: black;"
                        class="ng-star-inserted">CGST Rate: </span></td>
                    <td width="25%"><span
                        style="font-family: Calibri; font-size: 12px; color: black;" class="ng-star-inserted">2.5%</span></td>
                    <td width="25%"><span style="font-family: Calibri; font-size: 12px; color: black;"
                        class="ng-star-inserted">CGST Amount: </span></td>
                    <td width="25%"><span
                        style="font-family: Calibri; font-size: 12px; color: black;" class="ng-star-inserted">{gst_cgst_amount}</span></td>
                </tr>
                <tr>
                    <td width="25%"><span style="font-family: Calibri; font-size: 12px; color: black;"
                        class="ng-star-inserted">SGST/UGST Rate: </span></td>
                    <td width="25%"></td>
                    <td width="25%"><span style="font-family: Calibri; font-size: 12px; color: black;"
                        class="ng-star-inserted">SGST/UGST Amount: </span></td>
                    <td width="25%"><span
                        style="font-family: Calibri; font-size: 12px; color: black;" class="ng-star-inserted">{gst_sgst_amount}</span></td>
                </tr>
                <tr>
                    <td width="25%"><span style="font-family: Calibri; font-size: 12px; color: black;"
                        class="ng-star-inserted">IGST Rate: </span></td>
                    <td width="25%"><span
                        style="font-family: Calibri; font-size: 12px; color: black;" class="ng-star-inserted">5.0%</span></td>
                    <td width="25%"><span style="font-family: Calibri; font-size: 12px; color: black;"
                        class="ng-star-inserted">IGST Amount: </span></td>
                    <td width="25%"><span
                        style="font-family: Calibri; font-size: 12px; color: black;" class="ng-star-inserted">{gst_igst_amount}</span></td>
                </tr>
            </table>
        </td>
    </tr>
    <tr style="border-bottom: 2px solid #000000;">
        <td width="100%" style="padding: 0px 12px; font-family: Calibri; font-size: 12px; color: black; border-bottom: 2px solid #000000;">
            <span class="ng-star-inserted"><strong>Place of Supply:</strong></span>&nbsp;&nbsp;
            <span class="ng-star-inserted">{gst_place_of_supply}</span>&nbsp;&nbsp;&nbsp;
            <span class="ng-star-inserted"><strong>State Name/Code of Supplier:</strong></span>&nbsp;&nbsp;
            <span class="ng-star-inserted">{gst_state_name_code}</span>
        </td>
    </tr>
    <tr height="10px"></tr>
    <tr>
        <td style="padding: 0px 10px;">
            <table width="100%">
                <tr>
                    <td width="100%"><span
                            style="font-family: Calibri; font-size: 11px; color: black;"
                            class="ng-star-inserted"><strong><u>INSTRUCTIONS:</u></strong></span></td>
                </tr>
                <tr>
                    <td width="100%">
                        <table border="0" width="100%" align="center"
                            style="font-family: Calibri; font-size: 11px; color: black;" class="ng-star-inserted">
                            <tr class="ng-star-inserted">
                                <td valign="top" style="text-align: justify; padding: 0px;">
                                    <span style="font-family: Calibri; font-size: 11px;">1.</span></td>
                                <td valign="top" style="text-align: justify; padding: 0px 0px 0px 5px;">
                                    <span style="font-family: Calibri; font-size: 11px;">Prescribed Original ID proofs are:- Voter Identity Card / Passport / PAN Card / Driving License / Photo ID card issued by Central / State Govt. / Public Sector Undertakings of State / Central Government ,District Administrations , Municipal bodies and Panchayat Administrations which are having serial number / Student Identity Card with photograph issued by recognized School or College for their students / Nationalized Bank Passbook with photograph /Credit Cards issued by Banks with laminated photograph/Unique Identification Card "Aadhaar", m-Aadhaar, e-Aadhaar. /Passenger showing the Aadhaar/Driving Licence from the "Issued Document" section by logging into his/her DigiLocker account considered as valid proof of identity. (Documents uploaded by the user i.e. the document in "Uploaded Document" section will not be considered as a valid proof of identity).</span></td>
                            </tr>
                            <tr class="ng-star-inserted">
                                <td valign="top" style="text-align: justify; padding: 0px;">
                                    <span style="font-family: Calibri; font-size: 11px;">2.</span></td>
                                <td valign="top" style="text-align: justify; padding: 0px 0px 0px 5px;">
                                    <span style="font-family: Calibri; font-size: 11px;">PNRs having fully waitlisted status will be dropped and automatic refund of the ticket amount after deducting the applicable CLERKAGE by Railway shall be credited to the account used for payment for booking of the ticket. Passengers having fully waitlisted e-ticket are not allowed to board the train. However, the names of PARTIALLY waitlisted/confirmed and RAC ticket passenger will appear in the chart and will be allowed to board the train.</span></td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </td>
    </tr>
    </div>
</body>
</html>"""

# Base64 placeholders for logos (1x1 transparent PNG as fallback)
_RAILWAY_LOGO_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
_IRCTC_LOGO_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


class TicketRenderError(Exception):
    """Base exception for ticket rendering errors."""


class TicketRenderService:
    """Renders IRCTC Electronic Reservation Slip (ERS) tickets to HTML/PDF.

    Accepts a booking DTO dict matching the IRCTC ERS response structure
    and produces HTML with all placeholders substituted. Can export to
    PDF via QWebEnginePage.printToPdf().
    """

    def __init__(self) -> None:
        self._template = _ERS_HTML_TEMPLATE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_html(self, booking_dto: dict[str, Any]) -> str:
        """Render a booking DTO to ERS HTML.

        Args:
            booking_dto: Dictionary with keys matching the ERS template
                placeholders. Expected structure mirrors
                ticket-template.html placeholders (r.bookingResponseDTO.*,
                FullClassName, PassengerRowsPlaceholder, etc.).

        Returns:
            Complete HTML string with all placeholders substituted.

        Raises:
            TicketRenderError: If required fields are missing.
        """
        try:
            ctx = self._build_context(booking_dto)
        except KeyError as exc:
            raise TicketRenderError(f"Missing required field: {exc}") from exc

        html = self._template
        for key, value in ctx.items():
            html = html.replace("{" + key + "}", str(value))
        return html

    def render_passenger_rows(self, passengers: list[dict[str, Any]]) -> str:
        """Render passenger detail table rows.

        Args:
            passengers: List of passenger dicts with keys: name, age,
                gender, booking_status, current_status.

        Returns:
            HTML string of <tr> elements, one per passenger.
        """
        rows: list[str] = []
        for idx, p in enumerate(passengers, start=1):
            rows.append(
                "<tr>"
                f"<td width=\"3%\">{idx}</td>"
                f"<td width=\"19%\" align=\"left\">{p.get('name', '')}</td>"
                f"<td width=\"7%\" align=\"left\">{p.get('age', '')}</td>"
                f"<td width=\"9%\" align=\"left\">{p.get('gender', '')}</td>"
                f"<td width=\"25%\" align=\"left\">{p.get('booking_status', '')}</td>"
                f"<td width=\"25%\" align=\"left\">{p.get('current_status', '')}</td>"
                "</tr>"
            )
        return "\n".join(rows)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_context(self, dto: dict[str, Any]) -> dict[str, str]:
        """Flatten the nested booking DTO into a flat template context."""
        br = dto.get("bookingResponseDTO", {})
        gst = br.get("gstCharge", {})

        return {
            "HtmlTitle": dto.get("HtmlTitle", "Electronic Reservation Slip"),
            "railway_logo": _data_uri(_RAILWAY_LOGO_B64),
            "irctc_logo": _data_uri(_IRCTC_LOGO_B64),
            "pnr_number": br.get("pnrNumber", ""),
            "train_number": br.get("trainNumber", ""),
            "train_name": br.get("trainName", ""),
            "full_class_name": dto.get("FullClassName", ""),
            "journey_class": br.get("journeyClass", ""),
            "booked_quota": br.get("bookedQuota", ""),
            "journey_quota": br.get("journeyQuota", ""),
            "distance": br.get("distance", ""),
            "booking_date": br.get("bookingDate", ""),
            "from_stn_name": br.get("fromStnName", ""),
            "from_stn": br.get("fromStn", ""),
            "boarding_stn_name": br.get("boardingStnName", ""),
            "boarding_stn": br.get("boardingStn", ""),
            "resvn_upto_stn_name": br.get("resvnUptoStnName", ""),
            "resvn_upto_stn": br.get("resvnUptoStn", ""),
            "journey_date": br.get("journeyDate", ""),
            "boarding_date": br.get("boardingDate", ""),
            "dest_arrv_date": br.get("destArrvDate", ""),
            "transaction_id": dto.get("transactionId", ""),
            "total_fare": br.get("totalFare", ""),
            "service_charge_total": br.get("serviceChargeTotal", ""),
            "total_collectible_amount": dto.get("totalCollectibleAmount", ""),
            "qrbase64_string": dto.get("qrbase64String", ""),
            "passenger_rows": self.render_passenger_rows(
                dto.get("passengers", [])
            ),
            "gst_invoice_number": gst.get("invoiceNumber", ""),
            "gst_supplier_address": gst.get("suplierAddress", ""),
            "gst_sac_code": gst.get("sacCode", ""),
            "gst_gstin_supplier": gst.get("gstinSuplier", ""),
            "gst_taxable_value": gst.get("taxableValue", ""),
            "gst_cgst_amount": gst.get("cgstAmount", ""),
            "gst_sgst_amount": gst.get("sgstAmount", ""),
            "gst_igst_amount": gst.get("igstAmount", ""),
            "gst_place_of_supply": dto.get("placeOfSupply", "NA"),
            "gst_state_name_code": dto.get("stateNameCode", "Delhi/DL"),
        }


def _data_uri(b64: str) -> str:
    """Wrap a base64 string as a data URI for embedding in HTML."""
    return f"data:image/png;base64,{b64}"
