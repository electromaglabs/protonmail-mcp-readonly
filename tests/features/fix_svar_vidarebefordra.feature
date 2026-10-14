Feature: Vidarebefordra e-post
  Som en MCP-klient som vidarebefordrar mejl
  vill jag att innehåll, bilagor och kopiemottagare följer med
  så att mottagaren får hela originalet.

  Scenario: Ett nyhetsbrev med bara HTML vidarebefordras med sitt innehåll
    Given mitt konto är "me@proton.me"
    And ett nyhetsbrev med UID "60" som bara har HTML-innehållet "<p>Viktigt innehåll</p>"
    When jag vidarebefordrar mejlet med UID "60" till "bo@example.se" med texten "Läs detta"
    Then ska den vidarebefordrade texten innehålla "Läs detta"
    And ska den vidarebefordrade texten innehålla "Viktigt innehåll"
    And ska den vidarebefordrade HTML-versionen innehålla "<p>Viktigt innehåll</p>"

  Scenario: Bilagorna följer med när ett mejl vidarebefordras
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "61" med bilagan "räkning.pdf" av typen "application/pdf"
    When jag vidarebefordrar mejlet med UID "61" till "bo@example.se" med texten "Se bilaga"
    Then ska det vidarebefordrade mejlet ha bilagan "räkning.pdf" av typen "application/pdf" med samma innehåll
    And ska den vidarebefordrade texten innehålla "Fakturan bifogas"

  Scenario: Vidarebefordra med kopia och hemlig kopia
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "62" från "anna@example.se" med ämnet "SV: Avtal"
    When jag vidarebefordrar mejlet med UID "62" till "bo@example.se" med kopia till "cia@example.se" och hemlig kopia till "arkiv@example.se"
    Then ska svarets ämne vara "Fwd: Avtal"
    And ska svaret gå till "bo@example.se"
    And ska svaret ha kopia till "cia@example.se"
    And SMTP-mottagarna ska vara "bo@example.se, cia@example.se, arkiv@example.se"
    And ska svaret sakna headern "Bcc"
