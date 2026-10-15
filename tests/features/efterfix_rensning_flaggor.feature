Feature: Flaggemojin för England, Skottland och Wales bevaras
  Som användare av en LLM som läser min e-post
  vill jag att flaggorna för England, Skottland och Wales visas som de ser ut
  så att ett vanligt ämne inte förstörs och inte flaggas som misstänkt.

  Scenario Outline: En flagga med taggsekvens i ämnet behålls och flaggas inte
    Given ett mejl med ämnet "Heja <flagga>!"
    When jag hämtar mejlet med get_email
    Then ska ämnet vara "Heja <flagga>!"
    And ska suspicious_content vara tom
    And ska sanitized inte nämna ämnet

    Examples:
      | flagga    |
      | england   |
      | skottland |
      | wales     |

  Scenario: Taggtecken efter en svart flagga som inte bildar en känd flagga tas bort
    Given ett mejl med ämnet "Heja svart-flagga-med-dold-text!"
    When jag hämtar mejlet med get_email
    Then ska ämnet vara "Heja 🏴!"
    And ska suspicious_content nämna taggtecken
