Feature: Gömd HTML tolkas som i en webbläsare
  Som användare av en LLM som läser min e-post
  vill jag att modellen ser samma text som jag ser i e-postklienten
  så att en avsändare varken kan gömma text för mig som modellen läser
  eller gömma synlig text för modellen.

  Scenario Outline: Ett ostängt gömt element slutar när dess förälder stängs
    Given ett HTML-mejl med innehållet '<html>'
    When jag hämtar mejlet som text med get_email
    Then ska brödtexten innehålla "SYNLIG"
    And ska brödtexten inte innehålla "gomd"

    Examples:
      | html                                                               |
      | <div><span style="font-size:0">gomd</div>SYNLIG                    |
      | <div><p style="display:none">gomd</div>SYNLIG                      |
      | <table><tr><td style="display:none">gomd</table><p>SYNLIG</p>      |
      | <div><span style="visibility:hidden">gomd<b>mer gomd</div>SYNLIG   |

  Scenario Outline: Ett självstängande icke-tomt element gömmer det som följer
    Given ett HTML-mejl med innehållet '<html>'
    When jag hämtar mejlet som text med get_email
    Then ska brödtexten vara "Hej"

    Examples:
      | html                                                       |
      | <p>Hej</p><div style="display:none"/>SECRET</div>          |
      | <p>Hej</p><span style="font-size:0"/>SECRET</span>         |

  Scenario Outline: Djup nästling döljer inte en gömmande stil
    Given ett HTML-mejl med <antal> nästlade stilade element runt ett element med stilen "<stil>" som innehåller "SECRET"
    When jag hämtar mejlet som text med get_email
    Then ska brödtexten inte innehålla "SECRET"

    Examples:
      | antal | stil              |
      | 40    | font-size:0       |
      | 40    | visibility:hidden |
      | 500   | font-size:0       |
