Feature: Efter granskningen — rubriker, adresser och HTML-text i inkommande mejl
  Som en MCP-klient
  vill jag att även illasinnade eller ovanliga mejl tolkas snabbt och rätt
  så att ett enda mejl aldrig låser servern eller skickar ett svar till fel adress.

  Scenario: Ett jättelikt ämne med oavslutade kodade ord låser inte servern
    Given en IMAP-sida med ett mejl vars ämne är 200 vikta rader med "=?a?q?x" utan avslutning
    When sidans metadata parsas och tiden mäts
    Then ska det ta under 1 sekund
    And ämnet ska börja med "=?a?q?x=?a?q?x"

  Scenario Outline: Vanliga kodade ämnen avkodas som förut
    Given ett mejl med rubrikraden "Subject: <rubrik>"
    When jag hämtar mejlet med get_email
    Then ska ämnet vara "<ämne>"

    Examples:
      | rubrik                                             | ämne        |
      | =?utf-8?q?R=C3=A4ksm=C3=B6rg=C3=A5s?=              | Räksmörgås  |
      | =?UTF-8?B?w6XDpMO2?=                               | åäö         |
      | =?utf-8?q?Kommer_du=3F?=                           | Kommer du?  |
      | =?utf-8?q?Kommer_du??=                             | Kommer du?  |
      | =?iso-8859-1?q?f=F6r?= =?iso-8859-1?q?_dig?=       | för dig     |
      | Re: =?utf-8?q?m=C3=B6te?= idag                     | Re: möte idag |
