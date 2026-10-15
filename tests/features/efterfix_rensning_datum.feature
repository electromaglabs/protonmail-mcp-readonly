Feature: date_iso följer RFC 5322 för år och tidszoner
  Som användare av en LLM som läser min e-post
  vill jag att date_iso aldrig hittar på ett år eller en tidszon
  så att modellen inte jämför datum som är fel med flera timmar eller hundra år.

  Scenario Outline: Datum tolkas enligt RFC 5322
    Given ett mejl med datumet "<datum>"
    When jag hämtar mejlet med get_email
    Then ska date_iso vara "<iso>"

    Examples:
      | datum                              | iso                       |
      | Tue, 14 Oct 50 21:45:00 +0200      | 1950-10-14T21:45:00+02:00 |
      | Tue, 14 Oct 68 21:45:00 +0200      | 1968-10-14T21:45:00+02:00 |
      | Tue, 14 Oct 49 21:45:00 +0200      | 2049-10-14T21:45:00+02:00 |
      | Tue, 14 Oct 126 21:45:00 +0200     | 2026-10-14T21:45:00+02:00 |
      | Tue, 14 Oct 2026 21:45:52 CEST     | 2026-10-14T21:45:52       |
      | Tue, 14 Oct 2026 21:45:52          | 2026-10-14T21:45:52       |
      | Tue, 14 Oct 2026 21:45:52 -0000    | 2026-10-14T21:45:52+00:00 |
      | Tue, 14 Oct 2026 21:45:00 +02      | 2026-10-14T21:45:00+02:00 |
      | Thu, 31 Dec 2026 23:59:60 +0000    | 2026-12-31T23:59:59+00:00 |
