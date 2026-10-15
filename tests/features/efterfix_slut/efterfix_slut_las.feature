Feature: Andra verktyg fungerar medan en permanent radering väntar på Bridge
  Som en MCP-klient
  vill jag kunna använda andra verktyg medan delete_email(permanent=True) väntar
  upp till 45 s på att Bridge genomför en radering som först nekades med Code=2501,
  eftersom väntan bara gäller Bridges händelsehämtning och inte behöver anslutningen.

  Scenario: Ett annat verktyg svarar medan raderingen väntar
    Given att mejlet "<a@x>" ligger i "Trash" med UID "5" och i All Mail med UID "50"
    And att mejlet "<b@x>" ligger i "INBOX" med UID "1"
    And att Bridge svarar NO med Code=2501 på permanent radering i "Trash" och mejlen blir kvar
    When jag raderar UID-listan "5" i "Trash" permanent och samtidigt markerar UID "1" i "INBOX" som läst
    Then ska markeringen ha svarat medan raderingen fortfarande väntade
    And ska verktyget ge ett fel som nämner "finns kvar i Trash"
