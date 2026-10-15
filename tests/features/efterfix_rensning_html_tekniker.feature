Feature: Fler sätt att gömma text i HTML fångas
  Som användare av en LLM som läser min e-post
  vill jag att text som e-postklienten inte visar (genomskinlig, pytteliten, utanför skärmen,
  bortklippt eller i samma färg som bakgrunden) inte heller når modellen
  så att en avsändare inte kan gömma instruktioner i ett vanligt utseende mejl.

  Scenario Outline: Gömd text når inte brödtexten
    Given ett HTML-mejl med innehållet '<p>Hej</p><inner>'
    When jag hämtar mejlet som text med get_email
    Then ska brödtexten vara "Hej"
    And ska hidden_html räkna minst 1 gömt element

    Examples:
      | inner                                                                                     |
      | <span style="color:transparent">SECRET</span>                                             |
      | <span style="color:rgba(0,0,0,0)">SECRET</span>                                           |
      | <span style="font-size:1px">SECRET</span>                                                 |
      | <span style="font:0/0 a">SECRET</span>                                                    |
      | <span style="opacity:0.01">SECRET</span>                                                  |
      | <div style="position:absolute;left:-9999px">SECRET</div>                                  |
      | <div style="text-indent:-9999px;overflow:hidden">SECRET</div>                             |
      | <div style="position:absolute;clip:rect(0,0,0,0)">SECRET</div>                            |
      | <div style="width:0;overflow:hidden">SECRET</div>                                         |
      | <div style="background:#ffffff"><font color="#ffffff">SECRET</font></div>                 |
      | <div style="background:#000"><span style="color:#000">SECRET</span></div>                 |

  Scenario: Vit text på en färgad knapp syns
    Given ett HTML-mejl med innehållet '<td bgcolor="#0057b8"><a style="color:#fff">Läs mer</a></td>'
    When jag hämtar mejlet som text med get_email
    Then ska brödtexten vara "Läs mer"
