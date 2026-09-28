---
raw2md_version: 0.1.0
source: Schwamb (2014).pdf
engine: marker
inspection: gemini_api
post: gemini_api
converted_at: 2026-09-27
source_hash: ASnuYIKCpWkJkvKAUriFPm1aGnr5VCFMxhMDVliIrzs
status: ok
issues:
- headings
- heading_ladder
---
# Performance Monitoring and Numerical Modelling of a Deep Circular Excavation

# Tina Schwamb

Department of Engineering University of Cambridge

This dissertation is submitted for the degree of *Doctor of Philosophy*

# Declaration

I hereby declare that except where specific reference is made to the work of others, the contents of this dissertation are original and have not been submitted in whole or in part for consideration for any other degree or qualification in this, or any other University. This dissertation is entirely the result of my own work and includes nothing which is the outcome of work done in collaboration, except where specified in the text. This dissertation contains fewer than 65,000 words, excluding table of contents, tables, figures, titles, footnotes, references and appendices and 150 figures.

> Tina Schwamb February 2014

# Acknowledgements

First and foremost, I would like to express my deepest gratitude to my supervisor Prof. Kenichi Soga. His patience, motivation and detailed approach contributed significantly to this thesis and I am immensely thankful to have him as my supervisor.

I would like to thank Dr. Mohammed Elshafie and Prof. Robert Mair for their initiative and support with the field study and for their encouragement and advice throughout the course of my PhD studies. Many thanks also go to my thesis examiners Prof. Malcolm Bolton and Dr. Andrew McNamara for providing valuable suggestions and corrections.

Without my MSc supervisor Dr. Michael Brown and my close friend and MSc classmate Marianna I would probably not have reached this point. Thanks to their assurance and encouragement I applied to Cambridge.

I could not have done the field work without the invaluable help of the fibre optic team. The hard work and long days on site were more fun with the company of Chang Ye Gue, Dr. Fei Wang, Koson (Te) Janmonta, Dr. Loizos Pelecanos, Masanari Nakashima, Njemile Faustin, Peter Knott and Seda Torisu. Thank you all very much.

My sincere thanks go to JV MVB (Joint venture between Morgan Sindall, Vinci Construction Grands Projets and Bachy Soletanche), AECOM, SolData and Thames Water, especially to Ba Dan Nguyen, Clotilde Boquet, Jean-Christophe Galan, John Greenwood, Julian Gatward, Martin Stanley, Richard Sutherden, Sivilay Sayavong and the site operatives for their help, support and cooperation.

The sometimes challenging problems I faced in my FLAC model seemed much more manageable with the help of Krishna Kumar, Dr. Shun Uchida and Dr. Yu Sheng Hsu (Mott MacDonald) and I am very grateful for their support. Many thanks also go to Krishna Kumar for creating this LATEX template.

I would also like to thank Prof. Hongwei Huang, Dr. Dongmei Zhang, Dr. Fei Wang and the other students in Office 729 at Tongji University in Shanghai for inviting me to spend 3 months on an academic exchange and for the memorable

time I had there. Many thanks also go to Prof. Jun Jian and Dr. Xuesong (Jonathan) Cheng for their kind invitations to Zhejiang and Tianjin University.

My time in the GRO would not have been so enjoyable without my friends and colleagues. Thank you Ahmed, Cise, Denis, Djihan, Krishna, Leonard, Osama, Ouge, Samila, Shun, Te, Tim, Yemi and Ziyad. I am very grateful for the memorable time we spent together, for the support and encouragement from all of you. Special thanks go to Rakshya for sharing all the ups and downs of the PhD life while working side-by-side for almost 3 years.

I gratefully acknowledge the financial support I received from the George and Lillian Schiff foundation, the Centre for Doctoral Training in Photonics Systems Development and Thames Water to undertake this research.

Last but not least, I would like to thank my family, my boyfriend James and my friends, for always being there for me, for their encouragement, support and love.

# Abstract

For the design of deep excavations, codes and standards advise to base estimates of wall deflections and ground movements on empirical data. Due to the limited number of case studies on circular excavations it is nearly impossible to find comparable projects under similar conditions. Therefore designers have to adopt conservative approaches, which predict larger ground movements than probably occur in reality and thus lead to more expensive structures and protective measures.

Further uncertainty is induced for diaphragm wall shafts. The discontinuous nature of the wall due to the joints between the individual panels may cause anisotropic wall behaviour. There is a complete lack of understanding if, and how, the design of diaphragm wall shafts should consider anisotropic wall stiffness.

The construction of Thames Water's Abbey Mills shaft in East London provided a unique opportunity to monitor the structural performance and the ground movements of one of the largest shafts ever built in the UK. The 71 m deep excavation penetrates a typical London strata and one third is in unweathered medium to hard Chalk. The monitoring scheme included distributed fibre optic strain sensing instrumentation and conventional inclinometers in the shaft wall to measure bending and hoop strains, as well as wall deflections during several construction stages. Further inclinometers and extensometers were installed around the shaft to monitor surface and subsurface ground movements. The monitoring results were then compared to the initial PLAXIS design predictions. A further numerical investigation was conducted in FLAC2D which allowed a more flexible parametric study.

The measured bending moments during shaft excavation exceeded the predictions mainly in the wall sections in the Chalk group. It was found that this was caused by assigning a low cohesion to the Chalk to induce conservative ground movements, so that the Chalk yielded in the analysis. In reality however, it remained elastic and hence induced larger bending moments in the wall. For

future excavations in Chalk it is recommended to investigate the effect of a low and a high cohesion of the Chalk on the wall bending moment.

The hoop strain measurements indicate that the shaft has undergone a three-dimensional deformation pattern during a dewatering trial prior to shaft excavation.

The parametric study on wall anisotropy suggests that the shaft wall behaved like a cylindrical shell with isotropic stiffness, where the joints between the panels do not reduce the circumferential stiffness.

Further numerical simulations varied the shaft wall thickness and the at rest lateral earth pressure coefficient in the Chalk. The results showed that the wall thickness has a minor influence on its deflection and hence thinner walls might be feasible for future shafts. The at rest lateral earth pressure coefficient of the Chalk appeared to be appropriately picked with 1.0 in the initial design.

Above all, it was shown that wall deflections were very small with less than 4 mm. Correspondingly small ground movements were measured throughout shaft excavation. Empirical formulas on the other hand predict large settlements between 40 and 105 mm. Numerical predictions were much closer to the measurements and showed that small heaves occurred due to soil swelling caused by removal of overburden pressure. For future shaft designs it is hence advised against the use of empirical formulas derived from case studies under different conditions. It may furthermore not be necessary to implement expensive large-scale monitoring schemes, as it has been confirmed that ground movements around diaphragm wall shafts are minimal and that risks are low.

The findings from this study provide valuable information for future excavations, which can be applied to the shafts constructed for the forthcoming Thames Tideway Tunnel project.

# Contents

|   | Contents |                 |                                           | xi    |
|---|----------|-----------------|-------------------------------------------|-------|
|   |          | List of Figures |                                           | xv    |
|   |          | List of Tables  |                                           | xix   |
|   |          | Nomenclature    |                                           | xxvii |
| 1 |          | Introduction    |                                           | 1     |
|   | 1.1      | Preface         |                                           | 1     |
|   | 1.2      |                 | London Tideway Improvements               | 3     |
|   | 1.3      |                 | Aims and objectives .                     | 5     |
|   | 1.4      |                 | Organisation of thesis .                  | 6     |
| 2 |          |                 | Literature review on circular excavations | 7     |
|   | 2.1      | Preface         |                                           | 7     |
|   | 2.2      |                 | Shaft construction methods                | 8     |
|   | 2.3      |                 | Design of circular shafts                 | 14    |
|   |          | 2.3.1           | Overview                                  | 14    |
|   |          | 2.3.2           | Empirical approaches                      | 14    |
|   |          | 2.3.3           | Limit equilibrium .                       | 15    |
|   |          | 2.3.4           | Soil-structure interaction .              | 16    |
|   |          | 2.3.5           | Mobilized Strength Design method          | 19    |
|   | 2.4      |                 | Experimental and theoretical approaches   | 20    |
|   |          | 2.4.1           | Surface settlement                        | 21    |
|   |          | 2.4.2           | Structural wall behaviour                 | 32    |
|   |          | 2.4.3           | Subsurface settlement and earth pressure  | 40    |
|   |          | 2.4.4           | Wall installation effects .               | 45    |
|   | 2.5      |                 | Summary and key points .                  | 48    |

# Contents

| 3 |   |   | Fibre optic instrumentation | 49 |
|---|---|---|---|---|
|   | 3.1 |   | Overview of shaft construction and monitoring scheme | 49 |
|   | 3.2 Background of fibre optic technology . |   |   | 54 |
|   | 3.3 |   | Fibre optic installation | 58 |
|   |   | 3.3.1 | Overview | 58 |
|   |   | 3.3.2 | Pre-installation stage . | 60 |
|   |   | 3.3.3 | Main-installation stage . | 63 |
|   |   | 3.3.4 | Post-installation stage | 64 |
|   | 3.4 |   | Pretension clamps laboratory test . | 68 |
|   |   | 3.4.1 | Overview | 68 |
|   |   | 3.4.2 | Experimental set-up and data acquisition | 68 |
|   |   | 3.4.3 | Results and discussion . | 69 |
|   | 3.5 |   | Data acquisition . | 72 |
|   | 3.6 |   | Breakages and repairs | 73 |
|   | 3.7 |   | Data analysis . | 78 |
|   |   | 3.7.1 | Principle of the temperature compensation | 78 |
|   |   | 3.7.2 | Data analysis step by step | 80 |
| 4 |   |   | Conventional instrumentation | 87 |
|   | 4.1 | Overview . |   | 87 |
|   | 4.2 |   | Extensometers . | 88 |
|   |   | 4.2.1 | Automatic rod extensometers . | 88 |
|   |   | 4.2.2 | Manual magnet extensometers | 91 |
|   | 4.3 |   | Inclinometers | 91 |
|   |   | 4.3.1 | Overview, terminology and data analysis | 91 |
|   |   | 4.3.2 | Accuracy and errors | 96 |
|   |   | 4.3.3 | Error correction . | 98 |
|   | 4.4 |   | Levelling pins | 102 |
|   | 4.5 |   | Diaphragm wall survey | 102 |
| 5 |   |   | Monitoring results | 105 |
|   | 5.1 |   | Introduction | 105 |
|   | 5.2 |   | PLAXIS design | 105 |
|   | 5.3 |   | Shaft excavation . | 108 |
|   |   | 5.3.1 | Diaphragm wall curvature and bending moment | 108 |
|   |   | 5.3.2 | Diaphragm wall movement | 111 |
|   |   | 5.3.3 | Diaphragm wall hoop strain | 117 |

|   |     | 5.3.4      | Ground movement                                                     | 122 |
|---|-----|------------|---------------------------------------------------------------------|-----|
|   | 5.4 |            | Diaphragm wall construction                                         | 129 |
|   | 5.5 |            | Dewatering trial .                                                  | 132 |
|   | 5.6 |            | Annulus infill                                                      | 134 |
|   | 5.7 |            | Discussion of the fibre optic monitoring scheme                     | 136 |
|   | 5.8 |            | Summary of key findings                                             | 138 |
| 6 |     |            | Numerical simulation                                                | 139 |
|   | 6.1 |            | Introduction                                                        | 139 |
|   | 6.2 | Overview . |                                                                     | 139 |
|   | 6.3 |            | Modelling procedure                                                 | 141 |
|   | 6.4 |            | Constitutive soil models                                            | 144 |
|   |     | 6.4.1      | Overview                                                            | 144 |
|   |     | 6.4.2      | Mohr-Coulomb model                                                  | 144 |
|   |     | 6.4.3      | Stiffness degradation function                                      | 145 |
|   |     | 6.4.4      | Strain hardening/ softening model .                                 | 148 |
|   |     | 6.4.5      | Hoek-Brown model for Chalk .                                        | 150 |
|   | 6.5 |            | Constitutive wall model                                             | 150 |
|   | 6.6 |            | FLAC runs and parametric study                                      | 151 |
|   |     | 6.6.1      | FLAC1                                                               | 151 |
|   |     | 6.6.2      | FLAC2                                                               | 152 |
|   | 6.7 |            | Assumptions and limitations                                         | 154 |
| 7 |     |            | Parametric study and discussion                                     | 157 |
|   | 7.1 | Overview . |                                                                     | 157 |
|   | 7.2 |            | Structural performance .                                            | 157 |
|   |     | 7.2.1      | Simple versus advanced constitutive models                          | 157 |
|   |     | 7.2.2      | Effect of wall installation versus wished-in-place (WIP) assumption | 163 |
|   |     | 7.2.3      | Effect of wall stiffness and anisotropy                             | 165 |
|   |     | 7.2.4      | Effect of wall thickness and verticality .                          | 171 |
|   |     | 7.2.5      | Effect of Chalk stiffness                                           | 173 |
|   |     | 7.2.6      | Effect of lateral earth pressure coefficient of the Chalk .         | 174 |
|   | 7.3 |            | Ground movement                                                     | 176 |
|   |     | 7.3.1      | Shaft excavation                                                    | 176 |
|   |     | 7.3.2      | Diaphragm wall construction                                         | 182 |
|   | 7.4 |            | Summary of key findings                                             | 183 |

# Contents

| 8 |            |           | Summary and conclusion          | 185 |
|---|------------|-----------|---------------------------------|-----|
|   | 8.1        | Summary . |                                 | 185 |
|   | 8.2        |           | Main findings                   | 186 |
|   |            | 8.2.1     | Field instrumentation           | 186 |
|   |            | 8.2.2     | Field data                      | 188 |
|   |            | 8.2.3     | Field data in comparison        | 188 |
|   |            | 8.2.4     | Implications .                  | 190 |
|   | 8.3        |           | Recommendations for future work | 191 |
|   | References |           |                                 | 193 |

# List of Figures

| 1.1 | Lowering the cutter head portion of a 120 m long tunnel boring |   |
|---|---|---|
|   | machine (TBM) called 'Busy-Lizzie' into a 80 m deep shaft at |   |
|   | Beckton (Courtesy of Thames Water) . | 2 |
| 1.2 | Overview Lee Tunnel project (Courtesy of Thames Water) | 4 |
| 2.1 | Overview of several shaft construction methods | 9 |
| 2.2 | Diaphragm wall construction | 12 |
| 2.3 | Subgrade reaction and pseudo finite element (FE) methods . | 17 |
| 2.4 | Normalised surface settlement of three case studies and predictions | 26 |
| 2.5 | Surface settlement of centrifuge tests by<br>Lade et al.<br>(1981) in<br>comparison to predictions (prototype dimensions) | 28 |
| 2.6 | Laboratory tests from<br>Hagiwara et al.<br>(1998) and<br>Tobar and<br>Meguid<br>(2011) on surface settlement depending on lateral wall |   |
|   | movement | 30 |
| 2.7 | Results from<br>Kusakabe's<br>(1982)<br>unsupported axisymmetric cen |   |
|   | trifuge studies: Comparison of measurements with upper bound<br>predictions | 31 |
| 2.8 | Deflection of individual diaphragm wall panels compared with |   |
|   | FE<br>predictions for different excavation stages - reproduced from |   |
|   | Cabarkapa et al.<br>(2003) | 33 |
| 2.9 | Axisymmetric analyses with different circumferential stiffness - |   |
|   | reproduced from<br>Zdravkovic et al.<br>(2005) | 34 |
| 2.10 | Comparison of measured hoop force with predictions from a |   |
|   | numerical analysis and a<br>K0-analysis - reproduced from<br>Anag |   |
|   | nostopoulos and Georgiadis<br>(2001) | 35 |
| 2.11 | Displacements of diaphragm wall head - reproduced from<br>Marten |   |
|   | and Bourgeois<br>(2005) | 37 |
| 2.12 | Deflections of two diaphragm wall panels in comparison with |   |
|   | numerical analyses (Ariizumi et al.,<br>2000) | 38 |
| 2.13 | Kusakabe's<br>(1982)<br>measured and predicted failure surface | 39 |
| 2.14 | Lateral earth pressure and failure mechanism for axisymmetric |   |
|   | conditions | 41 |

| 2.15 | Kim et al.'s<br>(2013) measurements of lateral earth pressure for a cir |     |
|------|-------------------------------------------------------------------------|-----|
|      | cular excavation in comparison to their predictions and Rankine         |     |
|      | theory .                                                                | 43  |
| 2.16 | Effect of wall installation .                                           | 47  |
| 3.1  | Cross-sectional view of Shaft F at Abbey Mills with ground con          |     |
|      | ditions and pore water pressure distribution                            | 50  |
| 3.2  | Plan view of Shaft F at Abbey Mills with instrumentation details        | 51  |
| 3.3  | Construction and monitoring                                             | 52  |
| 3.4  | Principle of fibre optic (FO) strain sensing                            | 56  |
| 3.5  | Overview of FO equipment used in this study                             | 57  |
| 3.6  | Overview of cable arrangement on the same reinforcement cage            | 59  |
| 3.7  | Pre-installation stage                                                  | 61  |
| 3.8  | Main-installation stage                                                 | 65  |
| 3.9  | Fujikura pretension clamp                                               | 67  |
| 3.10 | Routing cables through ducting to safe measurement hut (Cour            |     |
|      | tesy of Thames Water)                                                   | 67  |
| 3.11 | Experimental test set-up                                                | 69  |
| 3.12 | Results pretension clamps laboratory test                               | 70  |
| 3.13 | Longitudinal section through panel with arrangements of<br>FO           |     |
|      | cables and detail of concrete cover at different locations              | 75  |
| 3.14 | Repair works in pictures (Courtesy of Thames Water)                     | 76  |
| 3.15 | Repair works to by-pass breakages                                       | 77  |
| 3.16 | Schematic overview of FO data analysis                                  | 79  |
| 3.17 | Strain versus chainage                                                  | 82  |
| 3.18 | Interpolation and auto-correlation of datasets .                        | 83  |
| 3.19 | Calculation of curvature                                                | 84  |
| 3.20 | Close up view of one pretensioned section of the hoop strain            |     |
|      | cable (HSC)                                                             | 86  |
| 4.1  | Overview and location of boreholes for inclinometers and exten          |     |
|      | someters in one array (A or B) .                                        | 89  |
| 4.2  | Inclinometers and extensometers at Abbey Mills site .                   | 90  |
| 4.3  | Inclinometer data analysis                                              | 94  |
| 4.4  | Example of depth position error (DPE) occurrence in J-shaped            |     |
|      | casing caused by different positions of the probe - reproduced          |     |
|      | from<br>Mikkelsen<br>(2003)                                             | 97  |
| 4.5  | Lateral movement over depth for inclinometer borehole AI3               | 100 |
| 4.6  | Identifying DPE for inclinometer borehole AI3                           | 100 |
| 4.7  | Principle of boundary condition and bias shift correction for shaft     |     |
|      | inclinometer readings taken at deeper excavation levels .               | 101 |
| 4.8  | Optical diaphragm wall survey                                           | 104 |
| 5.1  | Overview of PLAXIS model                                                | 107 |

| 5.2  | Diaphragm wall incremental curvature/ bending moment be               |     |
|------|-----------------------------------------------------------------------|-----|
|      | tween successive excavation levels from<br>FO<br>measurements and     |     |
|      | inclinometers                                                         | 109 |
| 5.3  | Diaphragm wall curvature/ bending moment at different exca            |     |
|      | vation levels from FO measurements and inclinometers                  | 110 |
| 5.4  | Lateral wall movement from shaft inclinometers in comparison          |     |
|      | with PLAXIS predictions at different excavation levels (positive      |     |
|      | = towards excavation)                                                 | 113 |
| 5.5  | Diaphragm wall survey, movement of capping beam targets               |     |
|      | perpendicular and tangential to shaft wall .                          | 115 |
| 5.6  | Original and magnified deformed shape of capping beam from            |     |
|      | optical diaphragm wall survey at different dates and excavation       |     |
|      | stages .                                                              | 116 |
| 5.7  | Culvert construction (Courtesy of Thames Water)                       | 118 |
| 5.8  | Diaphragm wall survey, level movement of capping beam targets         | 118 |
| 5.9  | Hoop strain (at HSC level) versus excavation level                    | 119 |
| 5.10 | Surface settlement from optical survey of levelling pins              | 123 |
| 5.11 | Subsurface settlement from rod extensometers                          | 125 |
| 5.12 | Subsurface settlement from magnet extensometer AE3                    | 127 |
| 5.13 | Lateral ground movement from soil inclinometers at different          |     |
|      | excavation levels (positive = towards excavation) .                   | 128 |
| 5.14 | Rod extensometer measurements during diaphragm wall con               |     |
|      | struction including panel excavation and concreting dates, as         |     |
|      | well as ground profile with anchor depth (right)                      | 130 |
| 5.15 | Hoop strain measurements before and during dewatering trial .         | 133 |
| 5.16 | Monitoring results from annulus infill                                | 135 |
| 6.1  | Overview of FLAC model                                                | 140 |
| 6.2  | Modelling diaphragm wall installation .                               | 143 |
| 6.3  | Modelling of excavation                                               | 143 |
| 6.4  | Stiffness degradation for London Clay and Lambeth Group Clay          | 147 |
| 6.5  | Strain-Hardening/ Softening (SHS) model: fitting piecewise lin        |     |
|      | ear functions to the effective stress friction angle and dilation     |     |
|      | angle from test RS17 taken from<br>Ventouras<br>(2005)                | 149 |
| 6.6  | Reducing wall thickness due to verticality of panels                  | 153 |
| 7.1  | FLAC's predictions on the effect of soil models on incremental        |     |
|      | curvature/ bending moment in comparison with<br>FO<br>measurements159 |     |
| 7.2  | FLAC's predictions on the effect of soil models on absolute cur       |     |
|      | vature/ bending moment in comparison with FO measurements             | 160 |
| 7.3  | FLAC's predictions on the effect of soil models on lateral wall       |     |
|      | movement in comparison with inclinometer data .                       | 161 |

| 7.4  | Investigating the difference between Mohr-Coulomb (MC) and               |     |
|------|--------------------------------------------------------------------------|-----|
|      | Hoek-Brown (HB) model for Chalk .                                        | 162 |
| 7.5  | FLAC's predictions on the difference between<br>WIP<br>or full wall      |     |
|      | installation                                                             | 164 |
| 7.6  | Circumferential stiffness versus wall depth for FLAC runs with           |     |
|      | anisotropic wall stiffness                                               | 165 |
| 7.7  | FLAC's predictions on the effect of wall stiffness/anisotropy on         |     |
|      | incremental curvature/ bending moment in comparison with<br>FO           |     |
|      | measurements                                                             | 167 |
| 7.8  | FLAC's predictions on the effect of wall stiffness/ anisotropy on        |     |
|      | lateral wall movement in comparison with inclinometer data .             | 168 |
| 7.9  | FLAC's predictions on the effect of wall stiffness/ anisotropy on        |     |
|      | hoop strain in comparison with FO data                                   | 169 |
| 7.10 | Construction of joint between diaphragm wall panels at Abbey             |     |
|      | Mills shaft                                                              | 170 |
| 7.11 | Rectangular excavation made from diaphragm walls and reason              |     |
|      | for anisotropy                                                           | 171 |
| 7.12 | FLAC's predictions on the effect of wall thickness                       | 172 |
| 7.13 | FLAC's predictions on the effect of Chalk stiffness                      | 173 |
| 7.14 | K0<br>Pressure in elements next to shaft wall for different<br>values of |     |
|      | the Chalk before and after wall installation                             | 174 |
| 7.15 | FLAC's predictions on the effect of the lateral earth pressure           |     |
|      | coefficient in Chalk                                                     | 175 |
| 7.16 | Empirical formulas by<br>New and Bowers<br>(1994) and<br>Geotechnical    |     |
|      | Consulting Group<br>(2007) applied to Abbey Mills shaft in com           |     |
|      | parison with highest rod extensometer sensors and PLAXIS and             |     |
|      | FLAC predictions                                                         | 178 |
| 7.17 | FLAC's predictions of excavation-induced ground displacement             | 179 |
| 7.18 | FLAC's predicted horizontal ground movements in comparison               |     |
|      | to inclinometer measurements AI2 and BI2 6 m behind shaft wall           | 180 |
| 7.19 | FLAC's predicted horizontal ground movements in comparison               |     |
|      | to inclinometer measurements AI3 and BI3 15 m behind shaft wall181       |     |
| 7.20 | FLAC's predictions of ground displacement during diaphragm               |     |
|      | wall installation                                                        | 182 |

# List of Tables

| 3.1 | Overview FO installation .                                                   | 59  |
|-----|------------------------------------------------------------------------------|-----|
| 3.2 | FO datasets during different construction stages                             | 73  |
| 5.1 | PLAXIS characteristic soil model input parameters .                          | 106 |
| 5.2 | PLAXIS design general input parameters                                       | 108 |
| 5.3 | dDPE<br>zfix<br>and<br>values for error correction for shaft inclinometers . | 114 |
| 5.4 | dDPE<br>zfix<br>and<br>values for error correction for soil inclinometers .  | 127 |
| 6.1 | FLAC model details .                                                         | 140 |
| 6.2 | Details of triaxial test used to determine stiffness degradation             |     |
|     | curve for London Clay (Gasparre,<br>2005)                                    | 146 |
| 6.3 | Details of triaxial test used for<br>SHS<br>model for Thanet Sand and        |     |
|     | Lambeth Group Sand (Ventouras,<br>2005)                                      | 149 |
| 6.4 | FLAC1 input parameters .                                                     | 155 |
| 6.5 | FLAC2 input parameters .                                                     | 155 |
| 6.6 | Parametric study                                                             | 156 |
| 7.1 | FLAC's predictions of maximum wall deflection, curvature and                 |     |
|     | bending moment for different wall thickness (Equation<br>3.10)               | 172 |

# Nomenclature

## Roman Symbols

*A* Distance between soil and excavation face of the bending strain cable (BSC)

*a* Constant for stiffness degradation function depending on field data

*A*0 Inclinometer raw data for 0° pass

*A*180 Inclinometer raw data for 180° pass

*A*check Checksum of inclinometer reading

*A*comb Combined *A*0 and *A*180 inclinometer reading

*A* cor comb Corrected combined inclinometer reading

*a*hb Hoek-Brown model material constant

*b* Inclinometer probe bias

*C*1,*C*<sup>2</sup> Integration constants

*c* ′ Cohesion intercept

*c*inter Interface adhesion/ cohesion

*c*<sup>u</sup> Undrained shear strength

*D* Shaft diameter

*d* Distance behind shaft wall

*D*<sup>d</sup> Disturbance factor

*d*DPE Value of depth position error

*d*<sup>e</sup> Deviation of a 500 mm interval

*E* Young's modulus of shaft wall

*E*<sup>d</sup> Drained Young's modulus of ground layers

# Nomenclature

*E*<sup>t</sup> Extent of settlement trough

*E*θ Young's modulus of shaft wall in circumferential direction

*E*<sup>u</sup> Undrained Young's modulus of ground layers

*f*cd Concrete design compressive strength

*f* hb Hoek-Brown yield function

*f* <sup>s</sup> Mohr-Coulomb shear yield function

*f* <sup>t</sup> Mohr-Coulomb tension yield function

*G* Shear modulus

*G*max Shear modulus at very small strain

*G*<sup>s</sup> Secant shear modulus depending on strain level

*GSI* Geological Strength Index

*H* Shaft excavation depth

*H*<sup>d</sup> Wall depth

*I* Second moment of area of 1 m wide section of shaft wall

*i* Inclinometer interval variable (*i* = 1 at bottom of casing)

*i*fix Interval of fixity for inclinometer bias correction

*K* Bulk modulus

*k* Metric inclinometer probe constant

*K*<sup>0</sup> Lateral earth pressure coefficient at rest

*K*<sup>a</sup> Lateral earth pressure coefficient under active conditions

*K*a,mob Lateral mobilised active earth pressure coefficient

*K*<sup>f</sup> Fluid bulk modulus

*m*<sup>b</sup> Hoek-Brown model material constant

*m*<sup>i</sup> Hoek-Brown model material constant

*n* Parameter depending on loading/ unloading for stiffness degradation function

*N*φ Mohr-Coulomb parameter

*p* ′ Mean effective stress *q* Deviatoric stress

*r* Shaft radius

*RE* Random error

*R*inter Interface strength reduction factor

*s* Hoek-Brown model material constant

*SE* Systematic error

*S*h,max Maximum horizontal ground surface movement

*S*<sup>v</sup> Ground surface settlement

*S*v,max Maximum vertical ground surface settlement

*t* Thickness of shaft wall

*t* ′ Effective thickness of ring structure due to verticality of panels

*T*0,*T*<sup>1</sup> Different temperatures

*TE* Total error

*u* Lateral wall deflection

*u*<sup>0</sup> Pore water pressure

*u*cumdev Cumulative deviation, inclinometer casing shape

*y* Inclinometer instrument reading

*z* Depth

*z*fix Depth for inclinometer bias correction

## Greek Symbols

*α* Empirical constant in settlement formula by New and Bowers

\(1994\)

*α*<sup>a</sup> Temperature-induced apparent or intrinsic strain, constant for all optical fibres = 19.47 µε/K

*α*<sup>f</sup> Factor relating real lateral earth pressure to Berezantzev's \(1958\)

active earth pressure by Ueno and Yokoyama \(1996\)

*α*<sup>n</sup> Net thermal expansion of the jacketed fibre

*α*<sup>t</sup> Factor for temperature compensation

∆*α*<sup>i</sup> Incremental inclination angle of shaft wall

# Nomenclature

∆*BM* Incremental bending moment of shaft wall

∆*E* Differential easting coordinate of optical survey

∆*ε* Incremental mechanical strain

∆*ε*<sup>r</sup> Incremental radial strain in shaft wall

∆*ε*s, ∆*ε*<sup>e</sup> Incremental strains between two datasets on the soil and excavation face of the BSC, respectively

∆*ε*comb Incremental combined temperature-induced and mechanical strain

∆*ε*<sup>r</sup> Incremental radial strain in shaft wall

∆*ε*rz Incremental shear strain in shaft wall

∆*ε*<sup>t</sup> Incremental temperature strain

∆*ε*<sup>θ</sup> Incremental hoop strain in shaft wall

∆*ε*soil,t,∆*ε*exc,t Incremental temperature-induced strain in the temperature cable

(TC) on soil and excavation face respectively

∆*ε*θ,comb Incremental combined temperature-induced and mechanical hoop strain

∆*ε*<sup>z</sup> Incremental vertical strain in shaft wall

∆*κ* Incremental curvature of shaft wall

∆*L* Vertical movement of extensometer anchors with respect to reference head

∆*L*ref Vertical movement of reference extensometer anchor with respect to reference head

∆*L* <sup>∗</sup> Baselined vertical movement of extensometer anchors

∆*N* Differential northing coordinate of optical survey

∆*ν*<sup>B</sup> Frequency shift of Brillouin peaks from initial Brillouin peak frequency at reference strain and temperature

∆*p*<sup>i</sup> , ∆*p*<sup>o</sup> Incremental horizontal stress on shaft wall from inside and outside the shaft, respectively

∆*S* Differential movement towards centre of shaft

∆*σ*<sup>r</sup> Incremental radial stress in shaft wall

∆*σ*rz Incremental shear stress in shaft wall

∆*σ*<sup>θ</sup> Incremental circumferential stress in shaft wall

∆*σ*<sup>z</sup> Incremental vertical stress in shaft wall

∆*σ*<sup>θ</sup> Incremental hoop stress in shaft wall

∆*T* Differential movement tangential to shaft wall

∆*θ* Incremental angle of tilt

∆*u* Incremental lateral wall deflection/ incremental lateral inclinometer casing deflection

∆*u*bias Lateral movement of inclinometer including bias error correction

∆*u*DPE Lateral movement of inclinometer including depth position error correction

∆*V* Differential level coordinate of optical survey

{*ε*˙} Strain vector

*ε*0,*ε*<sup>1</sup> Strains in optical fibre

*ε*<sup>a</sup> Axial strain

*ε*ap Axial plastic strain

*ε*comb Combined temperature-induced and mechanical strain

*ε*<sup>p</sup> Pretension induced in FO cable

*ε*<sup>s</sup> Shear strain (according to definition by Gasparre, 2005\)

*ε*<sup>v</sup> Volumetric strain

*γ* Shear strain (according to FLAC's definition)

*γ*Bent Density bentonite

*γ*bulk Bulk density of ground layers

*γ*dry Dry density of ground layers

*γ*ref Reference shear strain for strain reversal

*γ*<sup>u</sup> Reference shear strain for MSD

*γ*WetConc Density wet concrete

*λ* Wavelength of the wall bulge related to prop spacing

*λ*<sup>r</sup> Lateral earth pressure coefficient on radial planes

# Nomenclature

Poisson's ratio 1/ Optical pulse frequency launched into optical fibre  $\nu_0$ Frequency shift of Brillouin peaks from input frequency  $v_0$  $\nu_{\rm B}$ Poisson's ratio of shaft wall in plane of isotropy  $\nu_{rz}$ Poisson's ratio of shaft wall between anisotropic and isotropic  $\nu_{\theta r}$ direction  $\phi'$ Effective stress friction angle of ground layers Angle of rotation for optical diaphragm wall survey Figure 4.8c  $\phi_{\rm d}$ Interface friction angle  $\phi_{\rm inter}$ ψ Dilation angle ρg Unit weight of soil  $\{\dot{\sigma}\}$ Stress vector  $\sigma_1', \sigma_3'$ Principle effective stresses  $\sigma_{a}$ Datum stress equal to 98 kPa  $\sigma_{c}$ Unconfined compressive strength Uniaxial compressive strength  $\sigma_{\rm ci}$ Horizontal in situ earth pressure  $\sigma_{\rm h}$ Measured lateral earth pressure by Ueno and Yokoyama (1996)  $\sigma_{r}$ Berezantzev's (1958) active lateral earth pressure  $\sigma_{\rm rB}$  $\sigma^{\mathsf{t}}$ Tension cut-off  $\sigma_{\rm v}$ Vertical in situ earth pressure τ Shear stress Reference shear stress for strain reversal  $\tau_{\rm ref}$ θ Angle of tilt of inclinometer probe

## Acronyms / Abbreviations

BOTDA Brillouin Optical-Time Domain Analysis

BOTDR Brillouin Optical-Time Domain Reflectometry

BSC Bending strain cable

DPE Depth position error

FE Finite element

FO Fibre Optic

GIR Geotechnical Interpretative Report

HB Hoek-Brown

HSC Hoop strain cable

ICFEP Imperial College Finite Element Program

JV MVB Joint venture between Morgan Sindall, Vinci Construction Grands

Projets, Bachy Soletanche (Contractor)

LVDT Linear variable differential transformer mbgl metre below ground level

MC Mohr-Coulomb

MSD Mobilized Strength Design

SHS Strain-Hardening/ Softening

SLS Serviceability limit state

TBM Tunnel boring machine

TC Temperature cable

ULS Ultimate limit state

WIP Wished-in-place

# Chapter 1

## Introduction

## 1.1 Preface

With fast growing urban populations the need for sustainable and effective infrastructure is increasing. This includes an efficient transportation system, which, in congested cities, is only feasible under ground, as well as water and wastewater facilities, which have to cope with ever increasing quantities. London is currently undergoing several major construction projects, namely the Crossrail project and the London Tideway Improvements, to enhance their transportation and sewage systems, for which tunnels and deep excavations are being constructed in congested and sensitive areas.

The London Tideway Improvements includes the construction of a 25 km long tunnel underneath the river Thames, which will capture sewage overflow. Another 7 km long tunnel is built to conduct the wastewater to the treatment works in East London. Crossrail is a 118 km long high-speed rail, including 21 km twin-bore tunnel underneath central London, connecting Heathrow and Maidenhead in the West to Shenfield and Abbey Wood in the East. Eight central London stations allow rapid transportation to and from the city centre.

Tunnelling projects often require the construction of several deep excavations to lower the tunnel boring machine (TBM) to the tunnel drive or to retrieve it again, as for example shown in Figure 1.1. After tunnel construction, shafts can serve to access the tunnel, e.g. stations, or to conduit sewage. Smaller diameter shafts are usually used for ventilation purposes.

These deep excavations can be of rectangular or circular shape. Circular excavations are often the preferred construction method due to larger structural stiffness and the lack of propping inside the excavation. Nevertheless, in com-

Figure 1.1: Lowering the cutter head portion of a 120 m long TBM called 'Busy-Lizzie' into a 80 m deep shaft at Beckton (Courtesy of Thames Water)

parison to rectangular shapes, little attention has been paid to the performance of circular shafts. Well-documented case histories are limited while the database for rectangular excavations is much more comprehensive. Therefore designers often use conservative approaches which result in larger settlements than probably occur in reality. Hence the costs of the construction and the protective measures increase. The study by New and Bowers \(1994\) is one of the only well-documented case histories in the UK and is hence frequently referred to. The formula to estimate surface settlement around shafts is based on a specific geometry, ground conditions and construction method, and may not easily be transferred to different excavation conditions.

Another uncertainty associated with diaphragm walls is the discontinuous nature of the wall which is built from individual panels. In circular excavations the discontinuity is in circumferential direction, potentially reducing the shafts hoop stiffness, which has a major influence on structural performance and hence ground movements. Designers usually assume fully isotropic walls (i.e. full stiffness in circumferential direction), which may not be adequate for diaphragm wall shafts and may result in unsafe design.

The construction of the Lee Tunnel, an integral part of the £1.7 billion London Tideway Improvements, provided the opportunity to carry out a field study on a deep circular shaft to address these uncertainties (costs as estimated in 2004, Thames Water Utilities Limited, 2013\).

## 1.2 London Tideway Improvements

London's 150 year old Victorian sewage system was initially designed to deal with foul sewage assuming a population of about four million as well as surface run-off. Following heavy rainfall, the system was designed to overflow into the River Thames when necessary to prevent flooding. The 2011 census revealed that London has a population in excess of eight million; in addition, less frequent but heavier rainfall is now common and many green spaces are paved preventing natural drainage. As a result, discharges into the River Thames are now happening much more frequently – around once a week on average. Every year a total of approximately 39 million tonnes of sewage are discharged into the Thames \(Thames Water Utilities Limited, 2014\).

In 2000, Thames Water, together with the Environment Agency, the Department of Environment, Food and Rural Affairs and the Greater London Authority, conducted the Thames Tideway Strategic Study \(Thames Water Utilities Limited, 2013\) in order to assess the environmental impact of intermittent discharges of storm sewage on the River Thames. The comprehensive study concluded that not only discharges from combined sewer overflows have to be prevented, but also that London's major sewage treatment works need to be expanded to treat considerably more wastewater.

In line with these recommendations, Thames Water has developed a number of major engineering schemes to help stop sewers overflow and improve water quality in the River Thames:

- The Lee Tunnel project (Figure 1.2\)
- The Thames Tideway Tunnel project
- Improving London's five principal sewage works

The Lee Tunnel has an internal diameter of 7.2 m. With an average depth of 75 m below the ground it is London's deepest tunnel. It runs 7 km from the Abbey Mills Pumping Station complex to the Beckton Sewage Treatment Works in East London. Figure 1.2 illustrates the key components of the Lee Tunnel project, which requires the formation of five permanent large diameter shafts, three sited at Beckton and two at Abbey Mills. These shafts are some of the largest ever constructed in the UK. Figure 1.1 shows the Beckton Overflow shaft which served as a TBM launch shaft.

This thesis presents the details of a case study conducted at Abbey Mills Shaft F which has an external diameter of 30 m (Figure 1.2\). Due to its depth of

Figure 1.2: Overview Lee Tunnel project (Courtesy of Thames Water)

71 m the shaft penetrates mixed and challenging ground conditions. Its 1.2 m thick primary lining was constructed from twenty 84 m deep diaphragm wall panels. A comprehensive monitoring scheme, including fibre optic (FO) sensors, inclinometers, extensometers and optical surveys, has been implemented and is detailed in this thesis. The results of this study will allow designers to make more confident predictions of structural behaviour and ground movements for the deep excavations of the forthcoming Thames Tunnel project.

## 1.3 Aims and objectives

The aim of this thesis is to investigate the performance of circular excavations with respect to structural behaviour and ground movements. A detailed case study and careful numerical back-analysis were conducted to improve design assumptions for future shaft construction projects. In detail, this thesis pursues the following objectives:

**Enhance database:** The database of circular excavations contains a limited number of studies, which makes it difficult for designers to base estimates on previous experience, as advised by codes and standards. This study contributes to the database with a well-documented case history.

**Ground movement:** As a result of the limited knowledge concerning ground movements around shafts, conservative approaches such as New and Bowers \(1994\) are used which probably lead to larger movements being predicted than occur in reality. Therefore surface and subsurface ground movements are measured and compared to existing empirical approaches to determine their adequacy or inadequacy.

**Structural performance:** Curvatures, bending and hoop strains are measured to gain a better understanding of the shaft wall's structural performance with a special focus on a potential anisotropic wall stiffness. Anisotropy could be caused by the discontinuous nature of the diaphragm wall.

**Validate/ improve design assumptions:** The measurements are compared to the initial PLAXIS design. In addition, a further numerical model is built in FLAC to carry out a more flexible parametric study. This helps to understand whether the design assumptions were appropriate and how they can be improved.

Overall, this work aims to contribute a well-documented case study to the database of circular excavations and to improve the design assumptions for shafts under similar conditions. It is envisaged that the results will be directly applicable for the design of the forthcoming Thames Tideway Tunnel project, which includes several deep circular excavations.

## 1.4 Organisation of thesis

- **Chapter 2** provides an overview of common shaft construction methods and current design practice. Due to the very few field and model studies, which are examined in detail in this Chapter, design assumptions are conservative and highly uncertain.
- **Chapter 3** introduces construction method of Abbey Mills Shaft F and the implemented monitoring scheme. It focuses on the FO instrumentation and details the background principle, the installation procedure, the data acquisition and analysis.
- **Chapter 4** deals with the conventional instrumentation. Extensometers, inclinometers and optical surface settlement and diaphragm wall surveys are introduced. A focus is placed on the error correction methods for inclinometers.
- **Chapter 5** presents the monitoring results during shaft excavation in comparison to the initial design (carried out in PLAXIS). Ground and wall movements as well as structural bending and hoop strains are presented. Further data from the diaphragm wall construction, a dewatering trial prior to excavation and the annulus infill are also discussed.
- **Chapter 6** introduces the numerical model carried out in FLAC, which is developed to back-analyse the design and conduct a parametric study.
- **Chapter 7** presents the result of the numerical simulations from FLAC in comparison to the field data. The influence of constitutive soil models, wall installation, wall stiffness/ anisotropy, wall thickness, Chalk stiffness and lateral earth pressure coefficient is examined.
- **Chapter 8** summarises this thesis and its findings. It also gives suggestions for further work in this area.

# Chapter 2

## Literature review on circular excavations

## 2.1 Preface

Circular excavations are commonly used in the construction industry. In tunnelling projects they may serve a dual purpose when they are used to launch the tunnel boring machine (TBM) into the deep tunnel drive (Figure 1.1\); after construction they can be used to access the tunnel, e.g. staircases or lifts can be built into the shaft. Smaller diameter shafts serve ventilation purposes. In sewage treatment shafts are commonly built for pumping stations and drop shafts.

While rectangular excavations usually require propping when exceeding a depth of 5 m, circular shafts are structurally stable and make use of the hoop forces in the retaining structure. Therefore they usually do not require propping. This maximisation of space for construction operations, the reduction of bulk excavation and the simplicity of the construction sequence make the circular excavation a 'dramatically simple solution' as stated by Powderham \(2000\). Due to vertical and horizontal arching effects, earth loading on the walls is smaller than under plane strain conditions \(Wong and Kaiser, 1988\). The wall length can furthermore be reduced in comparison to a rectangular excavation with the same floor area and therefore provides an economic solution \(Gaba et al., 2003\).

The subsequent sections provide an overview of shaft construction methods, common design practice and field, model and theoretical studies on circular excavations.

## 2.2 Shaft construction methods

Deep excavations require the construction of a retaining wall. Several types of walls can be used. The main criteria for or against a particular method is the water tightness, which is crucial if the excavation is below ground water table, the shaft dimensions (diameter and depth), ground conditions and the sensitivity of the surrounding infrastructure to ground movements. Some walls are installed during the excavation and others are built prior to excavation.

CIRIA C580 \(Gaba et al., 2003\) and Puller \(2003\) review the most common methods:

**King post wall:** Vertical posts are driven into the ground prior to excavation. Horizontal timber sheets or pre-cast concrete elements are then placed between the post with increasing excavation depth and the posts are anchored into the ground behind the wall (Figure 2.1a\). This method is economical, it is however not feasible in perfectly cohesionless soils; it is limited in depth and not water tight. It may also cause larger ground movements due to the low wall stiffness.

**Sheet piling:** Sheet piles are driven into the ground and tied back with anchors as excavation progresses (Figure 2.1b\). This method is also not feasible in rock or soils with large boulders which hinders driving the sheet piles. It can however reach deeper and is water tight.

**Caisson sinking:** Rings of pre-cast concrete segments are erected and driven into the ground with a steel cutting edge installed at the lowest ring (Figure 2.1c\). A lubricant (usually bentonite) is filled into the annulus behind the wall, a calculated jacking force is applied and simultaneously the shaft floor is excavated \(Allenby et al., 2009\). This method is applicable in dry and wet conditions (water will fill up inside the excavation and can be pumped). It is usually used for small diameters shafts (2 to 6 m).

**Segmental linings:** As shown in Figure 2.1d the pre-cast concrete or cast-iron segments are put in place in an underpinning operation. To control ground movement the annulus behind the wall is filled with grout. This method is applicable in dry conditions and in soil that temporarily stands without support.

(a) King post wall (timber) ([http://www.](http://www.learnz.org.nz/) [learnz.org.nz/](http://www.learnz.org.nz/))

(b) Sheet piling ([http://www.aeyates.co.](http://www.aeyates.co.uk/spi-appleton-ltd) [uk/spi-appleton-ltd](http://www.aeyates.co.uk/spi-appleton-ltd))

(c) Caisson sinking \(Newman and Wong, 2011\)

(d) Segmental shaft lining ([http://www.](http://www.fpmccann.co.uk) [fpmccann.co.uk](http://www.fpmccann.co.uk))

(e) Shotcreting (<http://www.epidomos.gr>) (f) Secant piling ([http://kellergrundbau.](http://kellergrundbau.ae/) [ae/](http://kellergrundbau.ae/))

Figure 2.1: Overview of several shaft construction methods

**Shotcreting:** Shotcrete is pneumatically conveyed onto the surface as excavation is progressing. The surface may have mesh reinforcement pinned to it to achieve tensile strength, or short reinforcing fibres will be added to the mix. It is only feasible in dry conditions and in stable ground \(Thomas, 2009\).

**Contiguous piling:** The cast-in-place concrete piles are constructed with a spacing larger than the pile diameter, so there are gaps between the adjacent piles (typically ranging between 50 and 150 mm). Depth can be as deep as 55 m but in practice 25 m is usually not exceeded. This type of wall is only suitable for temporary support and does not provide water tightness.

**Secant piling:** Secant pile walls (Figure 2.1f\) are also made from cast-in-place concrete piles where adjacent piles overlap (spacing smaller than a pile diameter). Verticality tolerances usually limit depths to approximately 20 m; up to 40 m depth can be achieved with special tools. The structure is feasible to be used in wet conditions.

### Diaphragm walls

Diaphragm walls, also called slurry walls, are constructed prior to shaft excavation. Depths of around 50 m can be achieved with conventional grabs, but they cannot be used in bedrock. Hydrofraises on the other hand can penetrate very hard ground and reach up to depths of 100 m. Bachy Soletanche constructed one of the deepest ever diaphragm walls of 98 m depth and 1.8 m thick panels for the Thames Water Lee Tunnel project at Beckton \(Otta, 2012\).

The construction method of a diaphragm wall is schematically displayed in Figure 2.2a. Firstly a guide wall is constructed; then a grab or hydrofraise is used to excavate the trench under a suspension liquid. After the panel excavation the reinforcement cages are lowered into the trench. Concrete is then filled into the trench from the bottom and displaces the bentonite liquid, which is pumped from the top to the storage tanks. To create a tight wall primary panels are built with a spacing and secondary panels are added in-between.

The joints have to be constructed carefully to guarantee interlocking of adjacent panels and water tightness. Bilfinger Spezialtiefbau GmbH \(2013\) lists the most common joint construction methods:

- **Steel stop-end pipes:** The principle is displayed in Figure 2.2b; stop-end steel pipes are installed on the short sides of the panel where the pipe has the same diameter as the panel width. The pipe is removed after the initial concrete setting to create a half-circular panel end; if overdigging occurred, concrete may flow around the pipe which has to be removed when the adjacent panel is excavated \(Fuchsberger, 1975\).
- **Pre-cast reinforced concrete stop-end:** Pre-cast concrete panels (Figure 2.2c\) stay permanently in the ground. They are lowered into the trench along with the reinforcement. When the adjacent panel is being excavated it serves as guide for the grab.
- **Steel joint element:** A picture of steel joint element is displayed in Figure 2.2d. The element contains one or two elastic joint tapes which will be cast into the concrete. After the adjacent panel has been excavated the element (without the tapes) can be removed.
- **Panel versus panel joint:** At Abbey Mills shaft the hydrofraise cut into the concrete of the already constructed primary panels when excavating the trench of the secondary panels. Before installation the primary panels were prepared with styrofoam on the side of the reinforcement cage as shown in Figure 2.2e. This is important to ensure that the digging tool is cutting as straight as possible.

Especially for deep shafts it is important to construct panels as vertical as possible, so that enough overlap is guaranteed at depth. This is important to transmit hoop forces in circular shafts and to ensure water tightness. On board equipment helps monitoring tolerances and verticality values of 1:400 can be achieved (i.e. a 100 m deep wall would be 0.25 m off vertical).

Virollet et al. \(2006\) highlight that the thickness of the ring structure is further reduced by the rectangular nature of the diaphragm wall panels (Figure 2.2f\). At Abbey Mills this was less of a problem, as the long primary panels were excavated in three separate pieces as well as equipped with three trapezoidal reinforcement cages (Figure 2.2g\).

Diaphragm walls are very stiff structures which reduce ground movements during excavation; the installation of the wall can however cause ground movements.

(a) Installation procedure of diaphragm walls ([http:](http://www.bacsol.co.uk/techniques/retaining-walls/diaphragm-walls/) [//www.bacsol.co.uk/techniques/retaining-walls/](http://www.bacsol.co.uk/techniques/retaining-walls/diaphragm-walls/) [diaphragm-walls/](http://www.bacsol.co.uk/techniques/retaining-walls/diaphragm-walls/))

(b) Steel stop-end pipe - reproduced from Fuchsberger \(1975\)

(c) Pre-cast concrete stop-end

Figure 2.2: Diaphragm wall construction

(d) Steel joint element (Bilfinger Spezialtiefbau GmbH, 2013)

(e) Abbey Mills joint construction (Courtesy of Thames Water)

(f) Diaphragm walls create imperfect circle Virollet et al. (2006)

(g) Abbey Mills panel layout (Courtesy of Thames Water)

Figure 2.2: (Cont.) Diaphragm wall construction

## 2.3 Design of circular shafts

### 2.3.1 Overview

CIRIA reports are design aids which provide practical guidance in accordance with structural codes and exist for many different topics. The CIRIA C580 guideline \(Gaba et al., 2003\) deals with embedded retaining walls of any plan shape, but seems to mainly refer to excavations of non-circular shapes. However, due to the lack of specific guidelines for circular shapes CIRIA C580 \(Gaba et al., 2003\) is used by practitioners when designing circular shafts with embedded retaining walls. The design steps suggested are outlined below:

1. Estimate wall deflections and ground movements from case history data to check suitability of wall type and construction method.
2. Check ultimate limit state (ULS). This ensures that a structure does not collapse when subjected to the worst design load combination. To achieve a safety margin before actual collapse, the partial safety factor method is usually applied.
3. Check serviceability limit state (SLS). SLS refers to deflections or movements of a structure and the surrounding soil that shall not exceed a limiting value under working load. The characteristic unfactored design loading is applied.

### 2.3.2 Empirical approaches

The first step in the design process is to estimate the wall deflections and ground movements from case history data to check the suitability of the wall type and the construction method. This is in line with Eurocode 7 which states that 'a cautious estimate of the distortion and displacement of retaining walls, and the effects on supported structures and services shall always be made on the basis of comparable experience' \(British Standards Institution, 2004a, p.110). Eurocode 7 also notes that the SLS may be fulfilled if this cautious estimate is within the tolerance.

While Long \(2001\) for example compiled an extensive database for propped and cantilever non-circular excavations with data from more than 300 case histories, the number of field studies for circular excavations is very limited. This

does not allow designers to pick a case that matches in dimensions, soil conditions and construction method. Therefore current British design practice, for the estimation of surface settlement around circular excavations, mainly relies on one study carried out by the Transport Research Laboratory on the Heathrow Express Trial Tunnel \(New and Bowers, 1994\). Although this case study has not been confirmed, the Geotechnical Consulting Group's \(2007\) report on 'Settlement Estimation Procedure: Box Excavations & Shafts' for the Crossrail project is primarily based on New and Bowers' \(1994\) case study and engineering judgement. With only little back-up, conservatism and cautiousness has to be adopted, which may lead to uneconomic wall design, over-predictions of movements and higher protective measures for adjacent structures. Further field data is certainly required to confirm the adequacy or inadequacy of New and Bowers \(1994\) and establish the influence of parameters such as shaft diameter, construction method and ground conditions.

### 2.3.3 Limit equilibrium

The limit equilibrium approach can only be used for ULS. It assumes simple linear lateral stress distribution and full strength mobilisation of the soil at collapse conditions. It cannot be used to determine deformations for SLS, as the structure is close to collapse where deformations are large.

Two commercially available and commonly used design programs are Re-WaRD \(Geocentrix, 2011\) and STAWAL \(Oasys Ltd., 2007\), which give the required embedment depth and structural forces. As both programs are only available for two-dimensional plane strain analysis, designers would either need to use hand calculation for axisymmetric conditions, which is tedious and prone to error, or incorporate the hoop stiffness by equivalent propping, which is difficult to determine accurately.

The basis for limit equilibrium solutions is the assumption of an active earth pressure distribution. This is especially difficult to estimate for axisymmetric excavations due to vertical and horizontal arching. The approach does furthermore not take account of the beneficial earth pressure redistribution due to wall movement.

Due to the above mentioned shortcomings the limit equilibrium approach has often been replaced by soil-structure interaction methods which can justify both ULS and SLS, and take the beneficial stress redistribution into account.

### 2.3.4 Soil-structure interaction

CIRIA C580 \(Gaba et al., 2003\) considers soil-structure interaction approaches as more appropriate and economic, as wall movements and the redistribution of earth pressure can be considered. It can be divided into (1) the simpler approaches of subgrade reaction and pseudo finite element (FE) methods and (2) the more sophisticated approaches using FE or finite difference methods.

#### 2.3.4.1 Subgrade reaction and pseudo FE methods

The subgrade reaction method replaces the soil by linear horizontal springs (Figure 2.3a\). According to Simpson and Powrie \(2001\), speaking of plane strain conditions, this method generally gives similar bending moment predictions to FE programs, but coefficients of subgrade reaction are not easily determined. A software tool commonly used is WALLAP \(Gesolve, 2002\) which is designed for plane strain conditions. Designers using the subgrade reaction method for circular shafts need to account for the larger stiffness in comparison to plane strain conditions. Chandrasegaran et al. \(2006\) detail the procedure and advise to represent the cylindrical rigidity as continuous elastic vertical support on the excavation side of a plane strain wall. However, this seems to only crudely represent the hoop stiffness and does not take any potentially reduced circumferential stiffness nor its mobilisation into account.

The pseudo FE approach replaces the soil by an elastic continuum and according to Simpson and Powrie \(2001\) it realistically redistributes earth pressure (Figure 2.3b\). A program frequently used in retaining wall design is FREW \(Oasys Ltd., 2010\) which has again been designed for plane strain conditions. It is argued that it can still be used for axisymmetric excavations when movements are small due to propping so that vertical arching dominates \(Oasys Ltd., 2010\). It does however not consider the beneficial hoop effect.

For both subgrade reaction and pseudo FE methods the computation of initial active and passive earth pressures and their redistribution are conducted according to plane strain theory which overestimates values and is therefore on the safe but conservative side. CIRIA C580 \(Gaba et al., 2003\) furthermore highlights the crude characterisation of the soil stiffness and that ground movement cannot be obtained, i.e. the justification of SLS is not possible.

It is crucial for both limit equilibrium and soil-structure interaction methods that the results are critically examined and calibrated against reliable measurements of well-monitored case histories.

(a) Subgrade reaction model - reproduced from Simpson and Powrie \(2001\) (b) Pseudo FE model - reproduced from Oasys Ltd. \(2010\)

Figure 2.3: Subgrade reaction and pseudo FE methods

#### 2.3.4.2 Finite element and finite difference methods

Using FE or finite difference packages is the most common design method, as they can account for various features, such as complex soil constitutive behaviour, construction sequences, structural and support details and consolidation and groundwater effects, as well as provide ground movements. As a trade-off the analysis is very time-consuming and the quality of the results highly depends on the availability of appropriate soil models and input parameters. Common packages used are SAFE, PLAXIS, CRISP, FLAC, ABAQUS and DYNA.

##### Wall installation

When designing diaphragm or bored pile walls it is important to take the effect of wall installation into consideration, as the installation process may cause lateral stress relief (in overconsolidated soil) or increase (where lateral earth pressure values are below 0.5). Powrie et al. \(1998\) argues that the installation changes the stress state in overconsolidated clays which may affect the soil stiffness during excavation. Simulations assuming a wished-in-place (WIP) wall cannot predict ground movements related to the construction of the wall, which may be significant.

Several studies \(Conti et al., 2012; Gourvenec and Powrie, 1999; Lings et al., 1994\) give advice on how to incorporate the wall installation in FE analyses.

CIRIA C580 \(Gaba et al., 2003\) acknowledges the importance of wall installation, but notes that the detailed modelling of the wall installation would be excessive and that further research is required.

##### Soil models

Using an appropriate soil model in FE analyses is often crucial for an accurate representation. This includes non-linear and anisotropic soil behaviour.

Several studies have highlighted the importance of stiffness degradation for soil-structure interaction problems even at very small strain \(Burland, 1989; Jardine et al., 1986; Kung et al., 2007\). While strain at failure is large, it is small under working conditions and therefore small-strain stiffness plays a decisive role for deformations. Kung and Ou \(2006\) used the field results from the excavation of the Taipei National Enterprise Center and compared the wall deflections and surface settlements with numerical results. The best results were achieved with the Modified Pseudo-Plasticity model \(Kung, 2003\) which is a hyperbolic model incorporating small strain non-linear stiffness behaviour.

Natural soil is likely to behave in a transversely anisotropic manner due to its original sedimentation. Stiffness and strength depend on the direction and orientation of the applied stress \(Potts and Zdravkovic, 1999\). Wongsaroj \(2005\) compared numerical simulations and measured ground displacement fields (vertical and horizontal movements at surface and subsurface) caused by tunnel excavation through St. James's Park in London Clay. Even though the prediction of the anisotropic model did not entirely match the field data, it was closer than the isotropic. Laver \(2010\) improved Wongsaroj's \(2005\) model as further data on strength anisotropy and softening during triaxial extension had become available in the meantime. His constitutive model modified the yield surface size and rotation, used alternative parameters and added fissure softening to Wongsaroj's \(2005\) original model and therefore achieved a better fit of the field data.

Although extensive research has highlighted the importance of above mentioned factors, academia and practice diverge how to conduct numerical analysis. In practice it is still common to use linear-elastic perfectly plastic soil models without consideration of anisotropy. This is partly due to the high amount of work associated with understanding, measuring and characteris

ing input parameters for these complex soil models, which requires extensive ground investigation and laboratory testing. Therefore designers have to balance between model complexity and available data \(Soga and O'Sullivan, 2010\). However, accurate predictions of settlement cannot be achieved until simulations incorporate more realistic soil behaviour.

##### Wall stiffness

In practice it is common to model the shaft wall as fully isotropic. However diaphragm walls are made from a series of panels with joints, which may cause lower stiffness in circumferential direction. The exact mechanism is not fully understood. Especially for circular excavations this plays an important role, as deformations significantly increase when reducing the full hoop stiffness. This is further discussed in Section 2.4.2.1.

### 2.3.5 Mobilized Strength Design method

The Mobilized Strength Design (MSD) is a performance based design method extending the concept of limit equilibrium and used as an alternative to complex FE and finite difference simulations for deep excavations in soft soils. It is based on the conservation of energy, where the loss of potential energy by the formation of the trough must balance with the work done by deforming the retaining wall and the soil \(Bolton et al., 2010\). This principle was first applied to rigid and smooth cantilever walls by Powrie and Bolton \(1988\) and followed up by Osman and Bolton \(2006\) to include braced excavations.

In comparison to numerical analyses which require a large number of soil parameters when using complex constitutive models, MSD can perform SLS and ULS in a single step and account for soil non-linearity based on few parameters. Therefore a direct simple shear test is required to yield the stress-strain curve of a representative sample.

Lam \(2010\) and Bolton et al. \(2010\) investigated how MSD compares to numerical analysis and field data. MSD results fit numerical simulations carried out with the MIT-E3 model within ±30 %, which is satisfactory considering that no detailed account is taken for soil anisotropy. Comparisons to the measured wall deflections from 110 case histories of braced excavations demonstrate that the MSD predictions fit the field data with a factor of 1.4. They furthermore plotted the structural response ratio versus the soil-structure stiffness ratio from the 110 case studies and found that all field data fit an inverse relationship with a coefficient of determination of 0.964. From this they derived a simple formula to predict the maximum wall deflection ∆*u* normalised by the excavation depth *H* as follows,


$$\frac{\Delta u}{H} = \frac{\gamma_{\rm u}}{400} \frac{\lambda}{H} \left(\frac{\rho g H}{c_{\rm u}}\right)^2 \tag{2.1}$$

where *γ*<sup>u</sup> is the reference shear strain, λ is the wavelength of the bulge the wall is forming (this is related to prop spacing) and ρg is the unit weight of the soil.

Bolton et al. \(2010\) notes that this equation does not include the wall's bending stiffness EI. This shows that structural stiffness, across a range of walls from sheet piles to diaphragm walls, has a minor influence on the wall's deflection.

For circular excavations, Equation 2.1 is perhaps not applicable as the factor 1/400 was derived from field data of braced excavations. It may be difficult to apply MSD to circular excavations, where hoop forces increase the system's stiffness, as the derivation is based on plane strain plasticity theory.

## 2.4 Experimental and theoretical approaches

As outlined in Section 2.3 current design practice needs reliable and well-documented case studies to estimate ground movements and wall deflections and calibrate numerical models.

An extensive literature search for case histories on circular shafts since 1980 has been carried out. The search comprised some of the most relevant journals and conference proceedings as listed below:

- Géotechnique
- Proceedings of the Institution of Civil Engineers (ICE) Journal of Geotechnical – Journal of Geotechnical Engineering
- Canadian Geotechnical Journal
- ASCE Journal of Geotechnical and Geoenvironmental Engineering
- International Conferences on Soil Mechanics and Geotechnical Engineering (ICSMGE)
- International Conferences on Underground Construction in Soft Ground (Technical Committee 204)
- International Conferences on Physical Modelling in Geotechnics (Technical Committee 105)

In comparison to the database for propped and cantilever non-circular excavations by Long \(2001\) which includes more than 300 case histories, the result of this search is rather disappointing. Only 17 case studies of circular shafts were found (Table 2.1\). This small number renders it unlikely to fulfil the requirements imposed by codes and standards. CIRIA C580 \(Gaba et al., 2003\) and Eurocode 7 \(British Standards Institution, 2004a\) strongly recommend the use of comparable case studies when estimating wall deflections and ground movements. Comparable refers to parameters such as shaft dimensions, construction method and soil conditions. This lack of case studies clearly imposes difficulties when considering the specific conditions of the available case studies. It is furthermore important to calibrate numerical simulations with well-documented case histories.

The few existing full-scale case histories, as well as relevant model-scale case studies and theoretical approaches are reviewed in the following sections.

### 2.4.1 Surface settlement

#### 2.4.1.1 New and Bowers' (1994) case study and settlement prediction

There is one well-documented case study of a circular shaft frequently referred to in practice. It was conducted by the Transport Research Laboratory \(New and Bowers, 1994\) which measured surface settlement during a 26 m deep shaft sinking in London Clay for the Heathrow Express Trial Tunnel. Two arrays (S and T line) of five and six movement stations radiated from the shaft wall and were monitored. The settlement *S*v(*d*) measured at a distance *d* behind the shaft wall is normalised with the shaft excavation depth *H* and plotted versus *d*, which is also normalised with *H* (Figure 2.4a\). The S line data was subject to heavy plant movement and hence this data was discarded. The T line gave a maximum settlement *S*v,max of approximately 15 mm next to the shaft wall (*d* = 0) and a zone of influence that is approximately equal to the depth of the shaft *H* when the shaft was approaching full depth. A parabolic curve was fitted through the data to obtain an empirical formula for the surface settlement *S*v(*d*) behind the shaft wall,

$$S_{\rm v}(d) = \frac{\alpha (H-d)^2}{H} \tag{2.2}$$

Table 2.1: Overview of case studies on circular excavations

| Reference | Location | Ground conditions<br>thickness of layers [m]<br><b>Dredge level</b> | Wall<br>depth [m] | Wall thick-<br>ness [m] | Exc depth<br>H [m] | Diameter<br>D [m] | Ratio<br>D/H[-] | Construc- | Monitored and<br>documented parameters<br>(Monitored parameters<br>without documentation) |
|---|---|---|---|---|---|---|---|---|---|
| Anagnostopoulos<br>and Georgiadis<br>(2001) | Greece | 8 m loose silty sand<br>2.5 m loose sandy silt<br>medium dense silty<br>sand | 16 | 0.6 | 9 | 20.8 | 2.3 | diaphragm | wall hoop forces<br>wall bending moments |
| Ariizumi et al. (2000) | Tokyo,<br>Japan | 25 m sand & silt layers<br>24 m sand<br>11 m gravel<br>8 m sand & silt<br>clay | 70 | 1.2-<br>1.4 | 29 | 144 | 5 | diaphragm | earth pressure on wall<br>wall deflection<br>wall hoop stresses<br>vertical wall stresses |
| Cabarkapa et al.<br>(2003) | Dublin,<br>Rep. of<br>Ireland | 2 m made ground<br>1 m weather boulder clay<br>12 m up. black oulder clay<br>12 m brown boulder clay<br>3 m lo. black boulder clay<br>limestone | 32.5 | 1.5 | 27-<br>29 | 56.6 | 2 | diaphragm | wall deflections<br>(rebar strains)<br>(surface settlement)<br>(water table) |
| Enami et al.<br>(1996) | ? | 26 m alluvial fine sand<br>11 m diluvial clay/sand<br>mud stone | 36.5 | 1.4-<br>1.7 | 36.5 | 30.4 | 0.8 | open caisson<br>method,<br>reinforced<br>concrete<br>rings | earth pressure on wall<br>reaction force at<br>cutting edge<br>friction force on<br>peripheral surface |
| Gerolymos et al.<br>(2007) | Athens,<br>Greece | 8 m sandy clay<br>weathered conglo-<br>merate | 33.7 | 1.2 | 24.5 | 26.5 | 1.1 | Contiguous<br>pile wall | wall deflections<br>(soil displacements)<br>(water table) |
| Goto and Iguro<br>(1989) | Tokyo,<br>Japan | 16 m reclaimed sand/silt<br>10 m diluvial sand<br>18 m diluvial sand/silt<br>42 m diluvial sand<br>diluvial sand/silt | 100 | 1.2 | 46 | 68 | 1.5 | diaphragm | wall head movements<br>earth pressure on wall<br>(wall deflections) |
| Kim et al. (2013) | South<br>Korea | 6 m top soil<br>7 m weathered soil<br>weathered rock | 16.6 | 0.8 | 15 | 8 | 0.5 | H-piles &<br>ring wale | earth pressure on wall<br>(soil pressure)<br>(lateral soil movement)<br>(water level) |
| Marten and<br>Bourgeois (2005) | Nantes,<br>France | 2.8 m sandy & silty fillings<br>10 m clayey silts<br>10 m clay<br>1 m fine to coarse sand<br>weathered mice-slates<br>Sound Mica-slates | s 24 | 0.8 | 14.7 | 46.3 | 3.2 | diaphragm | wall deflections<br>wall head movement |
| McNamara et al. (2008); Morrison et al. (2004) | London,<br>UK | 26 m London Clay<br>14 m Lambeth Group<br>14 m Thanet Sand<br>Chalk | 40 | 0.35 | 40 | 8.2 | 0.2 | segmental<br>lining &<br>secondary<br>lining | wall deflections<br>(soil displacements)<br>(water table) |
| Muramatsu and<br>Abe (1996) | Musashino,<br>Japan | 8 m loam layers<br>15 m Musashino gravel<br>Tokyo layer group<br>Joso layer group | 98 | 1.2 | 60.3 | 28.2 | 0.47 | diaphragm | earth pressure on wall<br>water pressure on wall<br>wall stresses<br>wall deflections<br>surface settlement |
| New and Bowers<br>(1994) | London,<br>UK | 0.5 m made ground<br>3 m Taplow Terrace gravel<br>London Clay | 26 | ? | 26 | 11 | 0.42 | shaft<br>sinking | surface settlement |
| Parashar et al.<br>(2007) | Singapore | 10 m sand<br>5 m soft marine clay<br>deposits<br>old aluvium | 68.5<br>72.5 | 1.2<br>1.2 | 65<br>69 | 30<br>37 | 0.46<br>0.54 | diaphragm<br>diaphragm | wall deflection wall bending moment hoop strain (surface settlement) |
| Placzek and<br>Londong (1994) | Bottrop,<br>Germany | 14.5 m made ground<br>7.5 m silty sand<br>0.5 m coarse silt<br>marl | 31 | 1.3 | 27 | 44 | 1.6 | diaphragm | wall head movements<br>earth pressure on wall<br>water pressure on wall<br>basal heave<br>(surface settlement) |
| Powderham (2000, 2002) | London,<br>UK | 6 m Terrace gravels<br>London Clay | 40 | 0.9-<br>1.2 | 30 | 60 | 2 | contiguous<br>& secant<br>pile wall | wall deflections |
| Tan and Wang<br>(2013) | Shanghai,<br>China | 5 m firm silty clay<br>11 m soft muddy clay<br>4 m stiff silty clay<br>dense silty fine sand | 36 | 1 | 18 | 100 | 5.6 | diaphragm | wall deflections<br>bending stresses<br>hoop stresses |
| Walter and<br>Tarallo (1985) | Zeebrugge,<br>Belgium | 8 m hydraulic embank.<br>7 m sandy clay<br>7 m fine sand<br>9 m medium compact sand<br>Tertiary clay | 40<br>d | 1.2 | 20 | 88 | 4.4 | diaphragm | wall deflections<br>(wall head movement)<br>(soil displacements) |
| Wong and Kaiser (1988) | London,<br>UK | 7 m sand/clay layers<br>14 m till<br>clay shale | 20 | ? | 20 | 3.2-<br>2.4 | 0.16-<br>0.12 | shaft<br>sinking | (sub)surface settlement<br>hori. ground movement<br>earth pressure |

where  $\alpha$  is an empirical constant that depends on ground conditions and construction method; for this study  $\alpha = 6 \times 10^{-4}$  provided the best match. Although this formula is frequently used, it has drawbacks, such as neglecting the diameter of the excavation and the uncertainty of  $\alpha$ .

New and Bowers (1994) also measured the horizontal soil movement with moderate success. One array of boreholes was disturbed; the other showed consistent movements of approximately 5 mm.

#### 2.4.1.2 Settlement predictions for shafts in the Crossrail project

The Crossrail project, the construction of a major railway link underneath London, includes several box and circular excavations. The settlement estimation guidelines (Geotechnical Consulting Group, 2007) mainly rely on the above mentioned study by New and Bowers (1994). Geotechnical Consulting Group (2007) however add a dependency on the diameter D; the maximum vertical settlement  $S_{v,max}$  (which is equal to  $S_v$  at d = 0) is defined as

$$S_{\text{v,max}} = \alpha H \cdot \frac{D}{10 \,\text{m}} \tag{2.3}$$

which is slightly more conservative as New and Bowers (1994) due to high uncertainty. To avoid high values of settlement for large diameter shafts, an upper bound is set for D > 25 m

$$S_{\text{v,max}} = 15 \times 10^{-4} \cdot H \tag{2.4}$$

The extent of the settlement trough  $E_t$  is assumed to be 1H (for  $D < 10 \,\text{m}$ ) and 2H (for  $D > 25 \,\text{m}$ ); for diameters between  $10 \,\text{m}$  and  $25 \,\text{m}$  it is linearly interpolated. The formula for the settlement distribution is given in Equation 2.5.

$$S_{\rm v}(d) = S_{\rm v,max} \cdot \exp(0.5) \cdot \exp\left(-\frac{(d + 2E_{\rm t}/3)^2}{8E_{\rm t}^2/9}\right) \tag{2.5}$$

Case histories of circular shafts that can be used to reliably derive formulations for horizontal soil movement are almost non-existent. Therefore Geotechnical Consulting Group (2007) assume the same Gaussian distribution as for the settlement, which is the same method as for rectangular excavations. The maximum horizontal movement  $S_{h,max}$  is assumed to be equal to the maximum vertical settlement  $S_{v,max}$ , i.e.  $S_{h,max}/S_{v,max} = 1$ .

#### 2.4.1.3 Settlement predictions from 1 g model tests by Pairaudeau (2011)

Pairaudeau \(2011\) used 1 g small model tests in dry sand to investigate the surface settlement around circular shafts in relation to the diameter *D*. A set of four tests was carried out. The model shafts were all 500 mm deep and the diameters ranged from 100 mm to 400 mm. The settlement profiles were used to obtain empirical relationships for the maximum settlement *S*v,max (Equation 2.6\) and the extent of the trough *E*<sup>t</sup> (Equation 2.7\); both depend linearly on the diameter *D*,

$$\frac{S_{\text{v,max}}}{H} = 0.0008 \cdot \frac{D}{H} + 0.0008 \tag{2.6}$$

$$\frac{E_{\rm t}}{H} = 0.3 \cdot \frac{D}{H} + 0.12 \tag{2.7}$$

Pairaudeau \(2011\) modified the Gaussian settlement profile derived above by Geotechnical Consulting Group \(2007\) by normalising the parameters *d* and *E*<sup>t</sup> by *H*, as given below in Equation 2.8

$$S_{\rm v}(d) = S_{\rm v,max} \cdot \exp(0.5) \cdot \exp\left(-\frac{(d/H + 2E_{\rm t}/H)^2}{(8E_{\rm t}/9)^2}\right) \tag{2.8}$$

#### 2.4.1.4 Comparison to field data

Three approaches were introduced above: (1) New and Bowers \(1994\), (2) Geotechnical Consulting Group \(2007\) and (3) Pairaudeau \(2011\); these are plotted in Figure 2.4b using the dimensions of New and Bowers' \(1994\) shaft. The figure also contains New and Bowers' \(1994\) measurement points. As mentioned above, the formula by New and Bowers \(1994\) was based on the T line measurements. Geotechnical Consulting Group \(2007\) adopted a slightly more conservative approach due to limited evidence; it is however still fitting the data well. It can be seen that the formula based on very small 1 g model tests \(Pairaudeau, 2011\) predicts maximum settlement almost twice as large as New and Bowers \(1994\) and Geotechnical Consulting Group \(2007\). The extent of the settlement trough is however less than half the size in comparison to the other two formulas.

Several reasons for the mismatch of Pairaudeau's \(2011\) formula are possible. The ground conditions were different; whereas Pairaudeau \(2011\) used dry sand, the Heathrow trial tunnel was constructed in London Clay. Pairaudeau's (2011) formula is based on small 1 g model tests and therefore has limitations of being transferred to real scale. On the other hand, the measurements by New and Bowers \(1994\) have not yet been confirmed by another study with similar conditions.

Another well-documented case study was conducted by Muramatsu and Abe \(1996\) in layered soil in Tokyo (Table 2.1\). The extensive monitoring scheme for the 60 m deep diaphragm wall shaft of 28 m diameter also included the measurement of vertical and horizontal surface movement during diaphragm wall installation and excavation. Despite the large dimensions the maximum settlements in the immediate proximity of the shaft were only between 4 and 7 mm (diaphragm wall installation and excavation), while New and Bowers \(1994\) measured 15 mm. In Figure 2.4c the measurements along with the three formulas are plotted. All approaches overestimate the settlements significantly. This indicates that diaphragm wall shafts are likely to result in smaller ground movements than shaft sinkings.

The horizontal ground movements measured by Muramatsu and Abe \(1996\) are slightly above the values for the vertical settlement, e.g. monitoring line No. 1 predicts 4 mm settlement next to the shaft wall and 6 mm horizontal movement; for lines No. 2 and 3 the ratio *S*h,max/*S*v,max is also approximately 1.5, slightly above the Geotechnical Consulting Group's \(2007\) recommendation of 1.

Wong and Kaiser \(1988\) implemented a large monitoring scheme for a shaft sinking of 20 m depth and 3.2 m diameter in layered soil comprising sand, clay and till (Table 2.1\). The surface settlement measurements from their case study are included in Figure 2.4a; they are approximately between the measurements from New and Bowers \(1994\) and Muramatsu and Abe \(1996\). It is reasonable that the soil surface measurements by Wong and Kaiser \(1988\) are smaller than those by New and Bowers \(1994\), as the diameter of the shaft is smaller while the depth is similar. When applying the formula by Geotechnical Consulting Group \(2007\) which takes the shaft diameter into account, the predictions are slightly smaller than the actual measurements, but seem to match the data relatively well (Figure 2.4d\). Pairaudeau \(2011\) and New and Bowers \(1994\) overestimate the settlement.

(a) Overview of measurements of three case histories \(Muramatsu and Abe, 1996; New and Bowers, 1994; Wong and Kaiser, 1988\)

Figure 2.4: Normalised surface settlement of three case studies and predictions

(c) Data from Muramatsu and Abe \(1996\) in comparison to predictions

(d) Data from Wong and Kaiser \(1988\) in comparison to predictions

Figure 2.4: *(Cont.)* Normalised surface settlement of three case studies and predictions

#### 2.4.1.5 Comparison to centrifuge measurements

Lade et al. (1981) carried out centrifuge tests on circular shafts in dry sand. The model shaft was 450 mm deep and 115 mm in diameter. At a g-level of 111.8 this corresponds to a prototype shaft of 12.9 m diameter and 50.3 m depth. The surface settlement  $S_{\rm v}(d)$  at three points behind the wall at three different excavation depths ( $H=18\,\rm m$ , 33 m and 50 m) were recorded and are plotted in Figure 2.5. The measurements show that the majority of settlement occurred during Stage 2 ( $S_{\rm v}(2.5\,\rm m)=13\,\rm mm$ ); Stages 3 and 4 only cause a small increase ( $S_{\rm v}(2.5\,\rm m)=17$  and 21 mm respectively). This indicates that the ratio D/H might be a relevant factor for the settlement magnitude, i.e. that shafts with large diameters in comparison to their depth might undergo more relative settlement.

Figure 2.5: Surface settlement of centrifuge tests by Lade et al. (1981) in comparison to predictions (prototype dimensions)

The figure also contains the predictions from the three formulas discussed above. The maximum settlement predictions by New and Bowers (1994) and Geotechnical Consulting Group (2007) at Stage 2 fit the measurements well; however with increasing excavation depth both the formulas overestimate settlements. The extent of the settlement trough at Stage 2 is however underestimated by both formulas. The predictions by Pairaudeau (2011) again overestimate the maximum settlement behind the wall and underestimate the extent of the trough. Equation 2.8 however normalises d and  $E_t$  by H and

hence predicts larger settlements for shallower shafts with larger *D*/*H*-ratios, as confirmed by Lade et al.'s \(1981\) measurements.

The above comparisons show that adopting empirical formulas to shaft excavations in other ground conditions and with different construction methods is highly inconsistent. The empirical formulas have several deficiencies, as they neglect factors which are likely to influence movements significantly. The effects of ground conditions, dewatering scheme, geometry, construction method and workmanship have not been considered in the calculations. To make more confident prediction on ground movements for circular excavations under different conditions further field data is needed, which underpins the necessity of this study.

#### 2.4.1.6 Additional model tests

Model data on the other hand is obtained more easily, but has limitations. Transferring the results from centrifuge or 1 g studies to derive empirical relations to be applied to real field studies might not be appropriate, as model shaft exhibit differences to prototype shafts. However, this data can be used to calibrate theoretical models or computer simulations that can then be utilised to predict field behaviour \(Lade et al., 1981\).

Hagiwara et al.'s \(1998\) and Tobar and Meguid's \(2011\) research concentrated on earth pressure measurements acting on shaft walls in dry sand, but both also presented measurements of the surface settlement in relation to the displacement of the shaft wall.

Hagiwara et al.'s \(1998\) centrifuge model shaft had a diameter *D* of 120 mm and a depth *H* of 500 mm. Figure 2.6 presents the normalised surface settlement *S*v(*d*)/*H* with respect to the lateral wall movement *u*. The recorded settlement increased approximately linearly up to wall movements between 5 and 7 mm. Then the surface settlement increases more rapidly with wall movement (Figure 2.6\).

Tobar and Meguid's \(2011\) 1 g model shaft was 150 mm in diameter, 1000 mm deep and placed in dry sand. They incrementally increased the wall movement to *u* = 4 mm and recorded the surface settlement at two points behind the wall. Figure 2.6 shows the reproduced results of both studies in comparison. It can be seen that the surface settlement *S*v(*d*) normalised by the excavation depth *H* of both studies agrees well when considering the different distances behind the shaft wall *d*.

Figure 2.6: Laboratory tests from Hagiwara et al. \(1998\) and Tobar and Meguid \(2011\) on surface settlement depending on lateral wall movement

Kusakabe \(1982\) focused on the failure mechanism of unsupported axisymmetric excavation in soft clay by comparing analytical, numerical and centrifuge results. During centrifuge tests various parameters were monitored; among them the surface settlement at collapse. Two undrained and one drained test with a 188 mm deep model shaft were conducted varying the diameter between 60 and 77 mm. Figure 2.7 shows the results of the centrifuge tests compared with his upper bound predictions. For all three tests the settlement extended to approximately 0.7 *H*; the upper bound solution predicted a shorter extent of the trough. The magnitude of the settlement for the drained test agreed with the predictions while the two undrained tests did not match well.

Another finding was that the horizontal ground movements were small in comparison to the vertical movements, e.g. in the two undrained tests vertical movements of around 12 mm and horizontal movements of 1 to 2 mm were recorded. This yields ratios of horizontal to vertical maximum movement

*S*h,max/*S*v,max of 0.08 to 0.16 which does not agree with Muramatsu and Abe's \(1996\) measurements and Geotechnical Consulting Group's \(2007\) suggestion of *S*h,max/*S*v,max = 1.5 and 1, respectively.

It should be noted that Kusakabe's \(1982\) tests are based on unsupported axisymmetric excavations at failure, which are not suitable to use as a base for SLS settlement predictions.

Figure 2.7: Results from Kusakabe's \(1982\) unsupported axisymmetric centrifuge studies: Comparison of measurements with upper bound predictions.

### 2.4.2 Structural wall behaviour

#### 2.4.2.1 Wall anisotropy

Cabarkapa et al. \(2003\) presented results from a 28 m deep and 56.6 m diameter shaft in Dublin Boulder Clay (Table 2.1\). The predicted and measured wall deflections for different excavation stages for three representative panels are shown in Figure 2.8. Firstly, it can be observed that panel 6 exhibits significantly larger deflections than panel 15 indicating an asymmetrical deformation pattern. Secondly, the disagreement of wall movements, those measured and those computed by the Imperial College Finite Element Program (ICFEP), can be observed. This could be explained by the uncertainty of the input parameters for the soil and hoop stiffness of the shaft walls. The latter refers to a key point of the paper: Diaphragm walls and piled walls have joints and are therefore not continuous in the circumferential direction. In FE simulations the stiffness in the circumferential direction is therefore usually reduced. However, the factor of reduction is an area of high uncertainty. Cabarkapa et al. \(2003\) used a factor of 2 based on previous experience, but initially experimented with factors between 1 and 10 to obtain bounds for likely results. When comparing the measured wall deflections with the numerical predictions (Figure 2.8\), the reduction factor of 2 appears too large and the shape does not match well. On the other hand, it is also questionable how trustworthy the inclinometer data is.

Zdravkovic et al. \(2005\) who numerically investigated rectangular excavations using ICFEP also concluded that the horizontal stiffness of discontinuous walls has to be reduced (independent on the plan shape of the excavation). An indication on the magnitude of reduction is however not given. Several axisymmetric 'reference' analyses were carried out where the ratio of circumferential to vertical Young's modulus *E*θ/*E* was varied between 1 and 0. The maximum deflection of a wall with reduced stiffness of *E*θ/*E* = 1 × 10−5 is only approximately 60 % of the value obtained from a plane strain analysis, as shown in Figure 2.9. The 'stiff wall' where *E*θ/*E* = 1 gave negligible wall movements. Zdravkovic et al. \(2005\) consider such a simulation clearly unrealistic; however without any comparison to field data.

Cabarkapa et al.'s \(2003\) further observations even complicate matters. The deflections trends shown in Figure 2.8 indicated two phases: In phase 1 at shallow excavation levels (Figures 2.8a and 2.8b\) the diaphragm wall panels were discontinuous and behaved like independent cantilevers with larger move-

Figure 2.8: Deflection of individual diaphragm wall panels compared with FE predictions for different excavation stages - reproduced from Cabarkapa et al. (2003)

Figure 2.9: Axisymmetric analyses with different circumferential stiffness - reproduced from Zdravkovic et al. \(2005\)

ments at the top. In phase 2 (Figures 2.8c and 2.8d\) when the initial movement closes any gaps between the panels and activated the hoop stiffness, panels 15 and 20 started bulging at mid and lower depths with a rotation around the ring beam. This indicates that the hoop stiffness of the wall was not realistically modelled by generally reducing the circumferential stiffness by a factor, but that its mobilisation should have been taken into account. The amount of mobilisation can involve parameters such as time, magnitude of deflection, excavation depth and quality of joints.

Another study investigated hoop compression forces, Anagnostopoulos and Georgiadis \(2001\) present results from an instrumented shaft of 20.8 m diameter and 9 m depth constructed in sandy soil in Greece (Table 2.1\). The measured hoop forces in the circumferential direction of the 0.6 m thick diaphragm walls are compared to axisymmetric FE simulations (PLAXIS) and simple hand calculations using *K*0 earth pressures (Figure 2.10\). For both cases, the circumferential stiffness was not reduced despite the horizontal discon

tinuity of the diaphragm walls. Good agreement was obtained as shown in Figure 2.10 and the authors considered the hand calculations assuming the shaft as a circular hollow cylinder loaded with at-rest earth and pore-water pressures appropriate. They furthermore observed small bending moments at the final excavation stage and hardly any wall deflections. Therefore it might be argued that, in this case of short walls with good quality joints, the full hoop stress was mobilised from an early stage and contributed significantly to the structure's stiffness. Small movements would also not mobilise active earth pressure and therefore justify the good agreement with the simple *K*0-analysis.

Figure 2.10: Comparison of measured hoop force with predictions from a numerical analysis and a *K*0-analysis - reproduced from Anagnostopoulos and Georgiadis \(2001\)

A recent study by Tan and Wang \(2013\) on a 100 m diameter excavation of 18 m depth in Shanghai (Table 2.1\) measured hoop stresses in ring beams and the diaphragm wall in great detail. It was found that the stresses in the ring beams increased directly after their construction when excavation progressed. While the ring beams were only monitored once excavation level reached the particular depth, the stresses in the diaphragm walls could be monitored

throughout the shaft excavation. Maximum compressional hoop stresses in the circumferential rebars were approximately 40 MPa which is well within the allowable steel yield strength of 320 MPa. The measured stresses could however not be compared to design predictions, as this was carried out with a two-dimensional plane strain subgrade reaction program.

Parashar et al. \(2007\) made similar observations measuring hoop strain on three adjacent large diameter and deep excavations (Table 2.1\). Hoop stresses increased when excavation reached the level of hoop measurements and decreased when the base slab was cast. Both studies Tan and Wang \(2013\) and Parashar et al. \(2007\) did not compare their measured hoop forces with design and hence it was not possible to advise on potential anisotropy in the wall.

Anisotropy is usually accounted for with a global reduction factor, which is not yet fully understood and requires further research. As assumed by Cabarkapa et al. \(2003\), the detailed mechanism behind the reduced circumferential stiffness might be more complex than just applying a reduction factor. Stiffness may be mobilised with movement of the walls when gaps between the panels close.

This area is particularly important for circular excavations as the realistic modelling of the circumferential stiffness significantly influences the whole system's stiffness and therefore wall deflections, soil movements and surface settlement. Nevertheless, only little research has been carried out.

#### 2.4.2.2 Other case studies

Marten and Bourgeois \(2005\) presented results of a nearly 15 m deep excavation of 46.3 m diameter retained by 0.8 m thick diaphragm walls in France (Table 2.1\). Monitoring wall head movements and deflections, they found an asymmetric deformation pattern despite the symmetric structural and ground conditions (Figure 2.11\). With the help of three-dimensional FE simulations (CESAR-LCPC) it was shown that the influence of the asymmetric construction sequence was a crucial factor for the deformed shape. Another study by Placzek and Londong \(1994\) of a circular diaphragm wall excavation of 27 m depth and 44 m diameter also showed an asymmetric deformation pattern from the wall head monitoring. Movements towards the retaining soil of 32 mm and 24 mm were observed at two locations due to leakages in the wall. The study by Goto and Iguro \(1989\) of a 46 m deep excavation of 68 m diameter also showed an oval deformation pattern from the wall head monitoring.

Figure 2.11: Displacements of diaphragm wall head - reproduced from Marten and Bourgeois \(2005\)

Ariizumi et al.'s \(2000\) study on a 144 m diameter excavation presented wall deflections, circumferential and vertical stresses in the diaphragm walls. It was shown that bending stresses were dominant throughout the excavation and that temperature had a significant effect on the measured stresses. Figure 2.12 shows the lateral wall deflections in comparison with numerical predictions; analysis-2 which takes temperature variations into account represents the measurements better.

Some other case studies used monitoring schemes in the spirit of the observational method to ensure safe accomplishment and maximum economy given that design can be modified during construction \(Peck, 1969\). One of the main reasons for the implementation of a monitoring system is usually difficult circumstances, such as disturbed and unstable ground conditions or close proximity to other infrastructure. The former was the case for the construction of a 60 m diameter and 30 m deep shaft for London's Heathrow airport \(Powderham, 2000, 2002\). A maximum wall deflection of 15 mm was observed 25 m below ground level (mbgl) - approximately half of the predicted value, which allowed the implementation of design changes, such as a deeper excavation depth.

Figure 2.12: Deflections of two diaphragm wall panels in comparison with numerical analyses \(Ariizumi et al., 2000\)

The reports by Morrison et al. \(2004\) and McNamara et al. \(2008\) presented the design and construction of a 8.2 m diameter and 37.4 m deep shaft for Crossrail. Very tight constraints were placed on the ground movement due to proximity to piled foundations. Trigger values had been set in case excessive movements were recorded. As in the previous study, the measurements were approximately half of the predictions. This shows the conservatism that has to be adopted due to highly uncertain design assumptions.

Gerolymos et al. \(2007\) reported a case study for the shaft constructed for the opening ceremony for the Athens' Olympic Games. Design was carried out with the most probable and favourable conditions but also for the worst-case scenario which included unfavourable soil properties, water conditions and disregarded the hoop effect. For the final excavation step the favourable design predicted a maximum deflection of 13 mm at 12 mbgl, whereas the unfavourable conditions predicted 40 mm. Contingency measures were planned in case this scenario occurred which was not the case; the measured deformations agreed reasonable well with the predictions for the most probable conditions. However, the ratio between the upper and lower bound, 40 mm/12 mm, gives a factor of 3.3 which highlights the uncertainty of the construction.

#### 2.4.2.3 Model scale

Not much work at model scale has been done to observe wall deflections of circular excavations. As mentioned above, Kusakabe \(1982\) conducted extensive centrifuge tests and also measured lateral soil displacements of an unsupported excavation; however at collapse and not under working conditions. Figure 2.13 shows the observations and the measurements predicted by his upper bound theory which agree reasonably well. The upper part of the 185 mm deep excavation of 30 mm diameter (model scale) moves 8 mm vertically downwards while the lower part bulges 13 mm towards the excavation.

The field observations related to the mobilisation of hoop stiffness by Cabarkapa et al. \(2003\) have to date not been investigated in model studies and require further research - in the field as in the laboratory.

Figure 2.13: Kusakabe's \(1982\) measured and predicted failure surface

### 2.4.3 Subsurface settlement and earth pressure

#### 2.4.3.1 Theoretical approaches

For most design approaches it is essential to understand the failure mechanism and to have a good understanding of the earth pressure distribution on the wall. Both are linked very closely, as earth pressure theories are based upon the assumption of a failure surface. The classical earth pressure theory by Coulomb \(1776\) is based on the limit equilibrium of a sliding wedge and is well established for two-dimensional conditions.

Starting with Terzaghi \(1920\) extensive research has been conducted to establish relationships between wall movement and active earth pressure. However, most of these approaches are only valid for plane strain conditions. Designers using these formulas for axisymmetric cases neglect the beneficial arching effects and obtain more conservative results.

Much effort has also been made to extend these two-dimensional theories to axisymmetric conditions which was reviewed by Tobar and Meguid \(2010\). Analytical methods based on classical Rankine theory were proposed by Westergaard \(1941\) for small unlined drilled holes and extended by Terzaghi \(1943\) for large lined holes. Although Terzaghi's \(1943\) solutions agreed well with other proposed methods (Figure 2.14a\), the assumption of the plastic zone renders the theory inadequate according to Prater \(1977\). Coulomb's failure surface leading to a sliding mass cone with downward pointing tip (Figure 2.14b\) is a more realistic shape and was adopted for Prater's \(1977\) limit equilibrium approach (Figure 2.14a\). Berezantzev \(1958\) firstly extended the slip line method to axisymmetric conditions (Figure 2.14a\). Both, Prater \(1977\) and Berezantzev \(1958\), are however limited to *c* ′ or *φ* ′ soil only, to vertical, smooth walls and level ground \(Cheng et al., 2007\). Berezantzev's \(1958\) method was extended by Cheng et al. \(2007\) and Liu and Wang \(2008\) to included further parameters, such as wall friction, backfill slope, surcharge load and soil cohesion. Prater \(1977\) also highlighted the sensitivity to the earth pressure coefficient *λ*<sup>r</sup> , which is defined as the ratio of circumferential stress to vertical stress and determines the tangential force *T* due to the axisymmetric arching effect (Figure 2.14b\). He argued that the assumption of *λ*<sup>r</sup> = 1, as adopted by Berezantzev \(1958\) and Terzaghi \(1943\), underestimated the earth pressure. Therefore, Cheng and Hu \(2005\) modified Berezantzev's \(1958\) theory to include *λ*<sup>r</sup> as a parameter, with *λ*<sup>r</sup> = *K*<sup>0</sup> as a lower and *λ*<sup>r</sup> = 1 as an upper bound (Figure 2.14a\).

(a) Overview of several approaches to estimate lateral earth pressure for axisymmetric conditions

(b) Prater's \(1977\) wedge theory for axisymmetric conditions using tangential and radial force *T* and *F*

Figure 2.14: Lateral earth pressure and failure mechanism for axisymmetric conditions

Most of the above mentioned approaches are displayed in Figure 2.14a. It also includes the conventional plane strain distributions with the lateral earth pressure at rest *K*<sup>0</sup> and under active conditions *K*a, which are significantly higher than the pressures under axisymmetric conditions. The theories based on *λ*<sup>r</sup> = 1 produce the lowest lateral earth pressures, while *λ*<sup>r</sup> = *K*<sup>0</sup> is suggested for engineering applications to give a safe lower bound approximation \(Cheng and Hu, 2005; Prater, 1977\). It can be seen that the existing approaches vary significantly especially with increasing depth.

Tobar and Meguid \(2011\) highlight that there is high uncertainty of the required wall movement *u* to reach active conditions. Previous studies by Fujii et al. \(1994\), Herten and Pulsfort \(1999\) and Chun and Shin \(2006\) propose a wide range of values for the required wall movement *u* normalised by the excavation depth *H*, 0.05% ≤ *u*/*H* ≤ 1.8%, or normalised by the shaft diameter *D*, 0.07% ≤ *u*/*D* ≤ 3.3%. This is not surprising, as *u*/*H* and *u*/*D* are expected to vary according to the strain mobilisation. Vardanega and Bolton \(2011\) show that strain required to mobilise half the strength varies from about 0.1 % for low-plasticity silty clays to 3 % for high-plasticity clays.

#### 2.4.3.2 Experimental data

To remedy the uncertainty inherent to the above mentioned approaches it is essential to conduct field and model studies that can be compared to the theoretical data. As earth pressure is closely linked to the assumed failure mechanism, the measurement of both, the earth pressure itself and the subsurface movements, are equally important. A few case histories investigated the earth pressure acting on the shaft wall.

Enami et al. \(1996\) concentrated on earth pressure measurement during a caisson sinking of 36.5 m depth and 30.4 m diameter (*D*/*H* = 0.83, Table 2.1\). They found that the earth pressures above 10 m were approximately 2 times larger than predicted by a *K*<sup>0</sup> value of 0.5. Below 10 m depth the measured earth pressures were significantly lower than *K*<sup>0</sup> predictions. Kim et al. \(2013\) reported similar pressure distributions from the measurements at their field test shaft of 15 m depth and 8 m diameter (*D*/*H* = 0.53, Table 2.1\); the results are presented in Figure 2.15. At shallow depth the earth pressure is similar to the Rankine predictions, but at deeper depth the pressure decreases significantly. This shows that the arching effect of axisymmetric excavations and the nontriangular distribution is predominant for deep excavations with small *D*/*H*ratios. This is supported by field studies with large *D*/*H*-ratios \(Ariizumi et al., 2000; Goto and Iguro, 1989\) which show a triangular earth pressure distribution and no decrease with depth.

Muramatsu and Abe's \(1996\) earth pressure measurements of a deep shaft (*D*/*H* = 0.47) showed, against above theory, a triangular pressure distribution. They reported initial *K*0-values of 0.6 only dropped insignificantly to 0.5 after excavation. This small reduction is in line with the small surface settlement (Figures 2.4a and 2.4c\).

Unfortunately, the subsurface ground movements next to real axisymmetric excavations have not been reported much. During the works for the Heathrow express trial tunnel extensometers and inclinometers were used to record subsurface movements due to tunnelling, but not for the shaft excavation \(New and Bowers, 1994\). Wong and Kaiser \(1988\) used multi-point extensometers to measure vertical movement and inclinometers for horizontal movement. The purpose of the obtained measurement were the comparison to FE predictions, but no further conclusions were drawn.

In general it is difficult to get an overview of ground movements from field studies, as data is limited to the instrumentation locations, which is again

Figure 2.15: Kim et al.'s \(2013\) measurements of lateral earth pressure for a circular excavation in comparison to their predictions and Rankine theory

limited by the available budget. Therefore model tests, especially centrifuge tests, can provide a better picture of the failure mechanism.

In his centrifuges studies in undrained soft clay Kusakabe \(1982\) investigated the failure mechanism of unsupported excavation, as this is crucial for a good upper bound solution. Figure 2.13 presents the discontinuity lines obtained by his theoretical prediction (dashed lines) compared with the centrifuge results (continuous lines). Good agreement for the wall movement as well as for the inclined rupture zone is achieved, but not for the vertical slip surface. Therefore it cannot be clearly concluded whether the assumed failure mechanism is correct.

In their centrifuge tests in sand Lade et al. \(1981\) varied the radial stresses inside a circular excavation (*D*/*H* < 0.34) and measured earth pressure at different depths. They observed earth pressures slightly larger than Berezantzev's \(1958\) but much lower than at rest and active predictions.

While Lade et al. \(1981\) decreased stabilisation fluid pressure to simulate the excavation process, Ueno and Yokoyama \(1996\) used an in-flight excavator and conducted an extensive study on the flexibility of the shaft wall. Firstly, they again confirmed the underestimation of Berezantzev \(1958\) and the conservatism of Rankine's active earth pressure at depths deeper than two times the shaft radius. They secondly found that the stiffness of the lining dominates the magnitude of the earth pressure and established a fudge factor *α*<sup>f</sup> that relates the 'real' lateral earth pressure *σ*<sup>r</sup> (based on their measurements) to Berezantzev's \(1958\) active earth pressure *σ*rB

$$\alpha_{\rm f} = \frac{\sigma_{\rm r}}{\sigma_{\rm rB}} = 1 + 1.15 \cdot 10^{-4} \cdot \frac{Et/r}{\sigma_{\rm a}} \tag{2.9}$$

where *Et*/*r* is the apparent Young's modulus where *E* is the Young's modulus of the wall material, *t* is the wall thickness and *r* is the radius of the excavation. *σ*<sup>a</sup> is the atmospheric pressure datum equal to 98 kPa and used to make the formula's units consistent, but has no logical meaning. It is also difficult to apply the results of this idealised centrifuge test to apply to real-scale shafts.

Hagiwara et al. \(1998\) measured horizontal active and at rest earth pressure on centrifuge model shaft (*D*/*H* = 0.24) which were equipped with moving parts. At rest pressures were in agreement with the *K*<sup>0</sup> predictions. Only at a large wall movement of approximately *u*/*H* = 4 × 10−<sup>3</sup> (where *u* is the wall movement and *H* the excavation depth) the measurements agreed well with Berezantzev's \(1958\) values.

Tobar and Meguid (2010) concluded that the theoretical approaches are reasonable for shallow shafts with *H* < *D*, but there is high uncertainty for deep shafts with *H* > *D* due to the high influence of the ratio between vertical and horizontal arching at these depths. The upper bound solution, Berezantzev \(1958\) with *λ*<sup>r</sup> = 1, and the lower bound solutions, Prater \(1977\) and Cheng and Hu \(2005\) with *λ*<sup>r</sup> = *K*0, yield largely different earth pressures. Apart from this, there is a complete lack of understanding of the required wall movement for active conditions. Further studies of the failure mechanism and subsurface movement of real scale excavations as well as model studies are needed to establish more reliable approaches.

### 2.4.4 Wall installation effects

The earth pressure on a retaining wall does not only depend on wall movement, but can also change due to construction of the wall itself. Installation effects can be caused by the excavation of soil with a slurry wall grab or a hydrofraise and the use of stabilising fluid or fluid concrete \(Gunn and Clayton, 1992\). These effects may render the common numerical assumption of WIP walls as not appropriate. Neglecting installation effects, especially for heavily overconsolidated soils, such as London Clay, where the earth pressure coefficient *K*<sup>0</sup> can range between 1 and 2 at greater depth and up to 4 near the surface \(Hight et al., 2007\), can yield conservative results of earth pressure loading on the wall \(De Moor, 1994\). On the other hand, when considering installation effects but under plane strain conditions, the reduction of the lateral earth pressure can be overestimated. De Moor \(1994\) and Gourvenec and Powrie \(1999\) highlighted the importance of three-dimensional influences, such as horizontal soil arching and the installation sequence of diaphragm wall panels.

De Moor \(1994\) numerically investigated the stress relief due to wall installation and compared her results to Symons and Carder \(1993\). Using the two-dimensional FE program CRISP and focusing on stiff overconsolidated finegrained soils such as London Clay, De Moor \(1994\) analyses a plan (horizontal) section through a series of diaphragm wall panels rather than a cross-section. The results agree well with field data from Symons and Carder \(1993\) and suggest that initial *K*<sup>0</sup> in London Clay of 1.5 reduced to 1.1 after wall installation. De Moor \(1994\) furthermore produced non-dimensional graphs to estimate the change in lateral earth pressure for different panel geometries and stress changes.

Ng and Yan \(1999\) and Gourvenec and Powrie \(1999\) conducted full three-dimensional analyses of diaphragm wall installation and concluded that the amount of lateral stress relief decreases with panel length. Furthermore, they confirmed that the stress relief on a single panel could be partly reversed during the construction of neighbouring panels.

Sideri \(2012\) focused on the installation effect for circular excavations of different construction methods and varying diameter-to-depth-ratios in London Clay. Figure 2.16a shows the development of the lateral earth pressure coefficient (averaged over wall depth) throughout the construction of a diaphragm wall, determined from two-dimensional numerical simulations with ICFEP. The initial value of 1.44 reduces rapidly when the panels are excavated under

bentonite, but increases again during wall concreting. Concrete hardening decreases the earth pressure again and shaft excavation has almost no effect. Sideri \(2012\) also studies the influence of wall anisotropy (due to joints between the panels) on the earth pressure during shaft excavation. The excavation reduces the lateral earth pressure more significantly for walls with very low circumferential stiffness. For *E*θ/*E* = 1 × 10−<sup>5</sup> for example the lateral earth pressure coefficient reduces from 0.95 to 0.6 due to larger wall movements. For jacketed shafts the lateral earth pressure reduces progressively with increasing shaft depths Figure 2.16a).

CIRIA C580 \(Gaba et al., 2003, p. 255-259) lists a number of case studies conducted to investigate wall installation effects. Richards et al. \(2006\) for example thoroughly investigated the changes in horizontal water and earth pressure during installation of a bored pile wall and found a reduction of *K*<sup>0</sup> from 1 to 0.8 and no further change over 10 months after the installation. The changes in lateral loading due to borehole excavation, fluid and concrete pressure also resulted in surface settlement. This shows that 'even the most rigid diaphragm or secant pile wall cannot be totally effective in preventing loss of ground' \(Gunn and Clayton, 1992\).

Similar observations were made by Burland and Hancock \(1977\). They recorded the surface settlement behind a shaft wall of a rectangular excavation in London and found that approximately 50 % of the deformation had occurred during installation of the diaphragm wall. Muramatsu and Abe \(1996\) measured the horizontal and vertical movements around a circular shaft during wall construction, as shown in Figure 2.16b. From this it can be observed that again approximately half of the total horizontal and vertical ground movement had occurred during the construction process of the diaphragm wall. This is a significant amount that cannot be reduced by increasing wall stiffness, since it is inherent to the construction process.

Even for rectangular excavations where more field and case studies exist, CIRIA C580 \(Gaba et al., 2003\) states that 'it is difficult to give general advice on the magnitude and extent of lateral stress reduction during wall installation', as this depends on the in situ *K*~0~, soil and ground water conditions, pile or panel geometry, construction sequence and the detailed method. They generally suggest to reduce the lateral earth pressure coefficient to 1.0 (for overconsolidated soils) but use the in situ *K*<sup>0</sup> = 1 − sin*φ* ′ (for normally consolidated soils) where *φ* ′ is the effective stress friction angle.

(a) Development of lateral earth pressure coefficient (averaged over wall depth) throughout construction and excavation of a diaphragm wall shaft and a shaft sinking - reproduced from Sideri (2012)

(b) Vertical and horizontal surface displacement during wall installation and excavation reproduced from Muramatsu and Abe (1996)

Figure 2.16: Effect of wall installation

## 2.5 Summary and key points

This chapter reviewed the existing literature on circular excavations. Common shaft construction methods were discussed in Section 2.2. Section 2.3 highlighted that most existing design approaches were produced for plane strain conditions, whereas shafts are axisymmetric. A detailed review of on-going research, covering field and model studies, as well as theoretical approaches, was carried out in Section 2.4; the key points are summarised below.

The literature contains a very small number of well-documented case histories on circular excavations, while box excavations are significantly better documented. Thus, the British tunnelling industry relies on the study carried out by the Transport Research Laboratory on the Heathrow Express Trial Tunnel shaft sinking \(New and Bowers, 1994\). The formula has several limitations, such as not considering the shaft diameter, the construction method and the ground conditions. The settlement estimation guidelines for the Crossrail project Geotechnical Consulting Group \(2007\) are based on New and Bowers' \(1994\) formula, but include the shaft diameter, which results in very large settlements for large-diameter shafts.

The predictions from these empirical approaches were compared to the field measurements of two case studies, which showed highly inconsistent results. Especially for Muramatsu and Abe's \(1996\) diaphragm wall shaft the predictions were significantly larger than the measured data. Conservative design approaches resulting in larger settlements than probably occur in reality lead to more expensive structures and protective measures.

For diaphragm wall shafts further uncertainty arises from the discontinuous nature of the wall, as it is made of individual panels. Previous research \(Cabarkapa et al., 2003; Zdravkovic et al., 2005\) suggests that the wall's circumferential stiffness has to be reduced to account for the joints between the panels. A potentially lower hoop stiffness could have high influence on wall and ground movements. Only a few studies have investigated the wall anisotropy and hence there is a lack of understanding on how to incorporate this in design.

With the forthcoming Thames Tideway Tunnel for which several deep excavations are required, there is high need for a better understanding of ground movements and structural performance. This underpins the necessity for the field study at Abbey Mills to measure structural forces and ground movements around a shaft with a typical London geology.

# Chapter 3

#### Fibre optic instrumentation

## 3.1 Overview of shaft construction and monitoring scheme

The Abbey Mills Shaft F, one of the five shafts of the Lee Tunnel project (Figure 1.2\), is 30 m in external diameter and 71 m deep, as shown in the cross-sectional and plan views in Figures 3.1 and 3.2. Due to its depth it passes several ground layers, a typical London strata, and reaches as deep as the Chalk (Figure 3.1\). The hydrogeological conditions comprise a shallow and a deep aquifer, separated by the low permeability London Clay and Lambeth Group Clay layers.

The shaft's primary lining is made from twenty 1.2 m thick and 84 m deep diaphragm wall panels. At this panel depth a hydrofraise was needed to excavate the trenches. The wall was constructed between September and December 2011 (Figure 3.3a\); exact dates of the trench excavation and concreting of the individual panels are given in Figure 3.3b. The wider primary panels (even panel number) were installed first, so that the hydrofraise cut into the concrete of the primary panels when excavating the trench for the secondary panels. After diaphragm walling was completed, a 1 m high and 1.2 m wide capping beam was constructed at the top of the wall (Figure 3.1\).

Prior to shaft excavation for two days in February 2012, a dewatering trial was carried out (Figure 3.3a\). During the dewatering trial the deep aquifer's water level inside the to-be-excavated shaft was lowered from approximately 24 to 70 mbgl to test the groundwater cut-off of the diaphragm wall and the in situ permeability characteristics of the Chalk. Figure 3.3c shows the water levels inside the three dewatering wells during the trial.

#### Fibre optic instrumentation

The 71 m excavation of the shaft commenced in early April 2012 and was completed in early September 2012 (Figure 3.3a). Throughout excavation water was pumped from a sump at the excavation surface. After the construction of the 2 m thick base slab a 0.75 m thick secondary lining (double sided slipform shutter) was erected inside the shaft (Figure 3.1). The 0.6 m wide gap between the diaphragm wall and the secondary lining is called the 'annulus', which was filled with grout in April 2013 (Figure 3.3a).

Figure 3.1: Cross-sectional view of Shaft F at Abbey Mills with ground conditions and pore water pressure distribution

Figure 3.2: Plan view of Shaft F at Abbey Mills with instrumentation details

(a) Construction sequence timeline with monitoring periods and frequency

Figure 3.3: Construction and monitoring

(b) Diaphragm wall construction: Dates when panels were excavated and concreted

(c) Dewatering trial: Waterlevels in wells inside shaft

(d) Shaft excavation levels and FO readings

Figure 3.3: (Cont.) Construction and monitoring

An extensive monitoring scheme was employed to monitor the shaft performance during several construction stages. A plan view of the shaft with the locations of the instrumentation is provided in Figure 3.2. Three diaphragm wall panels P10, P15 and P20 were equipped with FO instrumentation, as well as with an inclinometer each. Two arrays of soil instrumentation boreholes for extensometers and inclinometers radiate from the shaft behind panels P15 and P20. Eight surface levelling pins and several targets on the diaphragm wall were surveyed optically.

Figure 3.3a gives an overview when the instrumentation was in place and when readings were obtained. The FO monitoring started in January 2012; several datasets were taken to monitor the diaphragm wall during the dewatering trial, shaft excavation (Figure 3.3d\) and the annulus infill.

The soil inclinometers and extensometers were installed by the sub-contractor SolData Ltd. in summer 2011, so that ground movement during diaphragm wall installation could be measured. SolData Ltd. read the manual instruments weekly, while the rod extensometers recorded automatically every 5 minutes.

During shaft excavation, the contractor conducted an optical survey of surface levelling pins and targets on the diaphragm wall, which was done manually every 4 days on average.

This chapter focuses on the FO instrumentation, its installation and data analysis. Other instrumentation apart from FO are discussed in Chapter 4.

## 3.2 Background of fibre optic technology

Distributed FO sensing is a novel technique which can be used to obtain distributed strain profiles along the length of a FO cable. A standard single-mode fibre can be embedded in concrete or attached to the surface of a structure in a configuration so that the required deformations can be measured.

Several techniques exist; for strain sensing Brillouin Optical Time-Domain Reflectometry/ Analysis (BOTDR/A) are most commonly used. For both, a short square optical pulse of frequency *ν*<sup>0</sup> (corresponding to a wavelength of 1500 nm) is launched into the fibre. Due to impurities in the glass the signal is back-scattered (Figure 3.4a\). BOTDR is based on spontaneous scattering while BOTDA relies on stimulated scattering, which provides higher accuracy of ±2 µε \(Omnisens SA, 2012\) in comparison to ±40 µε \(Yokogawa, 2005\). The BOTDA can however only be used if the cable has no breakage.

The back-scattered spectrum consists of a Rayleigh component of the same frequency as the launched optical pulse  $\nu_0$  and two components that have undergone a frequency shift, the Raman and Brillouin peaks, as shown in Figure 3.4b. The Brillouin frequency shift  $\nu_B$  is usually around 11 GHz at a wavelength of 1500 nm (Ohno et al., 2001). Its exact peak position varies linearly depending on temperature-induced and mechanical strain. The peak position  $\nu_B(\varepsilon_1, T_1)$  at strain  $\varepsilon_1$  and temperature  $T_1$  can be determined as follows,

$$\nu_{\rm B}(\varepsilon_1, T_1) = \nu_{\rm B}(\varepsilon_0, T_0) + \frac{\partial \nu_{\rm B}}{\partial \varepsilon} \cdot (\varepsilon_1 - \varepsilon_0) + \frac{\partial \nu_{\rm B}}{\partial T} \cdot (T_1 - T_0) \tag{3.1}$$

where  $\nu_{\rm B}(\varepsilon_0, T_0)$  is the peak position offset from  $\nu_0$  at a specific reference strain  $\varepsilon_0$  and temperature  $T_0$ , the coefficients are given by Ohno et al. (2001) as

$$\frac{\partial \nu_{\rm B}}{\partial \varepsilon} \approx 0.05 \frac{\rm MHz}{\mu \varepsilon} \tag{3.2}$$

$$\frac{\partial \nu_{\rm B}}{\partial T} \approx 1 \frac{\rm MHz}{\rm K} \tag{3.3}$$

Hence, the shift of the Brillouin peak from its initial position,

$$\Delta \nu_{\rm B}(\varepsilon_1, T_1) = \nu_{\rm B}(\varepsilon_1, T_1) - \nu_{\rm B}(\varepsilon_0, T_0) \tag{3.4}$$

can be used to obtain the combined temperature-induced and mechanical strain,

$$\varepsilon_{\rm comb} = \frac{\Delta \nu_{\rm B}}{0.05 \,\rm MHz/\mu\varepsilon} \tag{3.5}$$

In practice it is usually preferred to isolate the mechanical strain and compensate any temperature-induced strain. This is further detailed in Section 3.7.1.

By launching the pulse and keeping record of the time passing, the location of the scattered event along the fibre can be determined and a distributed strain profile obtained.

As the input light pulse has a finite width and at any time covers a finite length of the optical fibre, the strain measurements are averaged over this finite length which is called the spatial resolution. Two read-out units were used in this study: the Yokogawa AQ8603 BOTDR (Figure 3.5a) and the Omnisens DITEST STA-R BOTDA (Figure 3.5b), which feature a spatial resolution of 1 m (10 ns pulse width) and 0.5 m (5 ns pulse width), respectively.

The strain-sensing fibre used in this study is especially designed for the

rough construction environment, but is still flexible enough to fulfil the installation requirements; the 4-fibre ribbon is protected by a strong nylon sheet and two strength members (Figure 3.5c). As the Brillouin frequency shift is sensitive to strain and temperature this effect has to be compensated for. Therefore the unitube cable (Figure 3.5d) is installed alongside the strain cable and can be used for temperature compensation. The optical fibres swim in a gel liquid and are therefore not affected by mechanical strain. Once installed, baseline readings are taken. More measurements are recorded at further construction stages, so that the change in deformation can be obtained.

Further details on optical strain sensing can be found in the literature (Iten, 2011; Mohamad, 2008; Ohno et al., 2001).

(a) Principle of Brillouin strain sensing: Short light pulse launched into optical fibre, Brillouin frequency shifts where fibre is under strain (Ohno et al., 2001)

(b) Back-scattered spectrum comprising Rayleigh, Brillouin and Raman peaks. Brillouin peaks are linearly dependent on temperature-induced and mechanical strain

Figure 3.4: Principle of FO strain sensing

(a) BOTDR read-out unit AQ8603 by Yokogawa Electric Co., Ltd. \(Yokogawa, 2005\)

(b) BOTDA read-out unit DITEST STA-R by Omnisens SA \(Omnisens SA, 2012\)

(c) Schematical cross-section of strain sensing optical fibre cable by Fujikura Ltd., Japan \(Fujikura, 2009\)

(d) Schematical cross-section of temperature-induced strain sensing FO cable by Excel \(Mayflex Holidings Ltd., 2012\)

Figure 3.5: Overview of FO equipment used in this study

## 3.3 Fibre optic installation

### 3.3.1 Overview

Three panels were instrumented with FO cables, panels P10, P15 and P20, as shown in Figure 3.2. Panels P10 and P20 were primary panels which consisted of three reinforcement cages over their width which are called 'bytes' (indicated by the dashed lines in Figure 3.2\). For panel P10 the left byte (when facing the panel from the centre of the shaft) and for panel P20 the middle byte was instrumented. Since panel P15 was a secondary panel which is shorter in width, only one byte was installed.

Each reinforcement cage/ byte was equipped with a bending strain cable (BSC), a hoop strain cable (HSC) and a temperature cable (TC). A schematic overview of the cable arrangements on a reinforcement cage is shown in Figure 3.6. The BSC measures strain on the excavation and soil face which can be processed to wall curvature and hence bending moment. The HSC, arranged in a meander-shape with eight horizontal sections pointing in circumferential direction, provides the hoop strain in the diaphragm wall at a particular depth. To compensate the strain measurements from the BSC and the HSC for temperature-induced strain, a TC is installed in parallel to the BSC.

The FO cables were attached to the reinforcement bars. As each byte consisted of several pieces over the depth of the wall and the fibre had to be continuous over the splices between the pieces, the installation had to be carried out in three phases:

1. The pre-installation stage during which the pieces were prepared while lying on the ground
2. The main-installation stage when the cables were bridged over the splices and brought up to the top of the wall
3. The post-installation stage when the FO cables were routed to a data logging point

Table 3.1 provides further details on the installation; all three instrumented panels are listed including the type of panel (i.e. primary or secondary), the pieces1 used for pre-installation and the dates when pre-installation and the main installation were carried out.

<sup>1</sup>Reinforcement piece naming convention, e.g. P10 B1/2 = Panel P10, cage type B, byte 1 (1 = left facing panel from centre of shaft), 2nd piece from bottom

Figure 3.6: Overview of cable arrangement on the same reinforcement cage

Table 3.1: Overview FO installation

| Panel                      | P20           | P15           | P10        |
|----------------------------|---------------|---------------|------------|
| Primary/Secondary          | Primary       | Primary       | Secondary  |
| BSC pre-installation piece | P20 B2/1      | P10 B1/1      | P15 E1     |
| HSC pre-installation piece | P20 B2/2      | P10 B1/2      | P15 E3     |
| Date pre-installation      | 07/09/2011    | 14/10/2011    | 06/12/2011 |
| Date installation          | 29-30/09/2011 | 18-19/10/2011 | 07/12/2011 |
| Duration [hours]           | 14            | 10            | 6          |

### 3.3.2 Pre-installation stage

In the pre-installation stage the cages, while lying on the ground, were prepared for the main-installation stage.

Prior to the pre-installation, the FO cables were prepared in the laboratory, cut to the required length and coiled on cable drums (the total length of the cable was divided equally on two drums). The flat BSC were coloured on one side to ensure easy visual identification of any twists during installation, which could cause a breakage when the BSC was pretensioned.

It was important to make sure the reinforcement pieces were placed on higher wooden blanks than usual to allow the installation of FO cables on its underside (Figure 3.7c\).

The BSC and TC could then be attached to the bottom piece (piece 1) of the reinforcement cage (Figures 3.7a and 3.7d\). The TC was loosely fixed using cable ties, while the BSC required pretension. A pretension *ε*<sup>p</sup> of approximately 2000 µε was applied; this was found to be important for two reasons: firstly to measure compression and secondly to identify the two cable sections on the excavation and soil sides which have to be aligned carefully during the data analysis. Both cables were installed in parallel approximately 1 m apart to avoid tangling during the subsequent main-installation (Figure 3.7d\).

The HSC was attached to the 2nd piece from the bottom (piece 2) where the maximum hoop strain was predicted. For panel P15 this was not possible due to the future tunnel opening and the 3rd piece from the bottom (piece 3) was used. Figures 3.6b, 3.7b and 3.7e show the arrangement of the HSC in meander shape. The horizontal sections were pretensioned to *ε*<sup>p</sup> ≈ 2500 µε.

To apply pretension on the BSC and the HSC special plastic clamps were used, fabricated by Fujikura Ltd. Japan. As shown in Figures 3.7d to 3.7f the clamp was placed into a stainless steel seat; stainless steel was a requirement due to its position in the concrete cover. Welding stainless steel onto the reinforcement could be carried out without any problems by a welder on site while the pieces were lying on the ground.

It was important to stabilise the BSC and the HSC around the clamp to avoid any large bends and hence breakages during concreting of the diaphragm wall. At Abbey Mills strong wire and tape were used to add strength to the FO cable as shown in Figure 3.7f.

A 10 m reference bottom loop was prepared for each of the three cables. For the strain cables, BSC and HSC, the cables were wrapped around the cage along the links. The TC was coiled in a small loop and attached to the rebars.

(a) BSC and TC at piece 1 in loop configuration

(b) HSC on piece 2 from bottom for panels P10 and P20 (piece 3 for panel P15)

Figure 3.7: Pre-installation stage

(c) Pieces on higher wooden blanks to enable installation on the underside (Courtesy of Thames Water)

(d) TC (left) and BSC (right) on piece 1 (Courtesy of Thames Water)

(e) HSC on piece 2 from bottom (Courtesy of Thames Water)

(f) Protection of FO cable on loose side of clamp (Courtesy of Thames Water)

(g) Cable drums temporarily tightened to cage (Courtesy of Thames Water)

(h) Protection steel pipe welded to last piece at top of wall (Courtesy of Thames Water)

Figure 3.7: *(Cont.)* Pre-installation stage

The spare cables, still coiled on the cable drums, were temporarily attached to the reinforcement (Figure 3.7g\) in anticipation of the main-installation.

It was also necessary to fix a protection pipe to the top of the last piece (piece 6) through which the FO cables were threaded during the main-installation stage (Figure 3.7h\). This protected the FO cables when the top of the wall was cut off for the construction of the capping beam. The length of the pipe was approximately 1.5 m.

### 3.3.3 Main-installation stage

A few days after the pre-installation, the pieces of the reinforcement cage were lowered into the bentonite-supported trench and connected together. It had to be guaranteed that the FO cables were continuously bridged over the splices between the pieces. Furthermore, the BSC had to be pretensioned over the whole depth of the wall. This procedure is schematically shown in Figure 3.8a and is best explained as follows:

1. The bottom piece 1 with the pre-installed BSC and the TC was lowered into the trench (Figure 3.8b\).
2. When the top of piece 1 reached ground level the cable drums with the spare FO cables were taken off the reinforcement and placed on the cable drum stands (Figure 3.8c\).
3. Piece 2 with the pre-installed HSC was lifted over piece 1 and both pieces were connected (Figure 3.8c\). During this procedure reinforcement bars might need to be cut off; therefore a welding blanket was used to protect the FO cables from sparks (Figure 3.8d\).
4. Pieces 1 and 2, now connected, were then lowered into the trench. Simultaneously the BSC and TC were uncoiled from the cable drums. Care had to be taken that the BSC was not twisted (a twist might cause breakage when being pretensioned). As the cable was coloured on the outside a twist could easily be identified and prevented. The TC was loosely brought up and fixed with cable ties every 3 m approximately.
5. When the top of piece 2 reached ground level the HSC drums were added onto the cable drum stands.

6. The BSC was attached to the reinforcement at the top of every piece. It was pretensioned using the Fujikura clamps (Figure 3.8e\). The mechanism of the clamp is explained in detail in Figure 3.9:
   - (a) The plastic clamp was prepared beforehand to ensure the right amount of pretension (Figure 3.9a\).
   - (b) During installation the cable was inserted into the clamp (without its lids) which was then placed into a stainless steel seat that had previously been welded onto the reinforcement (Figure 3.9b\).
   - (c) The FO cable was pulled straight without any tension. Then the lids were screwed on to fix the FO cable tightly into the clamp (Figure 3.9c\).
   - (d) Nut 1 is then screwed downwards by the pre-determined distance to apply the required amount of pretension (Figure 3.9d\).
7. Piece 3 could then be spliced onto piece 2 and the above described procedure was repeated several times until all six pieces were lowered into the trench. The HSC cable was also loosely fixed like the TC.
8. When the top of piece 6 reached ground level, the FO cables were threaded through the steel protection pipe (Figure 3.8f\). The pipe had a vertical slot, so that the remaining length of FO cables did not have to be unrolled from the drums. This pipe later protected the fibres when the top of the wall was broken.
9. After concreting the panel the cable drums were stored temporarily near the top of the panel as shown in Figure 3.8g.

### 3.3.4 Post-installation stage

When all the panels and the capping beam were constructed, all FO cables were routed to a safe and clean working environment (Figure 3.10a\) approximately 30 m away from the shaft. The ducting, embedded into the temporary concrete platform, was specifically installed to protect the FO cables and the conventional instrumentation from the heavy site traffic (Figures 3.2 and 3.10b\).

Figure 3.8: Main-installation stage

(b) Lifting bottom piece with BSC and TC drums attached into trench (Courtesy of Thames Water)

(c) Splicing two pieces together and cable drum stand (Courtesy of Thames Water)

(d) Welding blanket to protect FO cables (Courtesy of Thames Water)

(e) Applying pretension with Fujikura clamps (Courtesy of Thames Water)

(f) Protection pipe at top of wall (Courtesy of Thames Water)

(g) Temporary storage of cables (Courtesy of Thames Water)

Figure 3.8: *(Cont.)* Main-installation stage

Figure 3.9: Fujikura pretension clamp (a) Step 1: Prepare clamps, determine required pretension distance between nuts, (b) Step 2: Unscrew lids and insert fibre. Step 3: Place nut 1 on metal seat, (c) Step 3: Manually tighten fibre and screw lids on to fix fibre in the clamp, (d) Step 4: Screw nut 1 downwards until metal seat is tight between nuts

Figure 3.10: Routing cables through ducting to safe measurement hut (Courtesy of Thames Water)

## 3.4 Pretension clamps laboratory test

### 3.4.1 Overview

As detailed above special clamps were used to pretension the BSC at several points on the reinforcement cage (Figure 3.9\). Since these clamps were used for the first time, laboratory tests were carried out to check the performance of the clamps. The following objectives were investigated:

- Ability of the clamps to keep the pretension over a period of 1 week
- Accuracy of BOTDR measurement when gradually applying and removing pretension and elastic behaviour of the Fujikura strain cable
- Linearity of relationship between BOTDR strain and clamp revolutions
- Dependency of results on different optical cores inside one cable

### 3.4.2 Experimental set-up and data acquisition

The experimental set-up is displayed in Figure 3.11. Two metal seats were rigidly attached to a stone wall (indoors). The FO cable of 9200 mm total length was prepared with two connectors at one end (the connectors were spliced onto two out of the four fibre cores inside the cable, Figure 3.5c\), referred to as 'blue' and 'brown' connector. Both connector cable lengths were the same, 940 mm, to allow for direct comparison of the readings without horizontal correlation. The strain induced in the fibre was also measured with two linear variable differential transformers (LVDTs). Those were attached so that they touch the end of the clamps and therefore measure their movement.

The first readings were taken on the loose fibre lying on the floor; two readings from each connector (dataset L ). Then the clamps were used to attach the FO cable to the wall as shown in Figure 3.11. The fibre was manually pulled until it was just tight, but not under a high amount of tension; again readings were taken (dataset 0 ). Then the nuts of one of the two clamps were turned by three, six, nine and twelve revolutions (datasets 3 , 6 , 9 and 12 ); for every dataset readings from both connectors were taken.

After reaching 12 revolutions, the pretension was incrementally removed again from 12 to 0 revolutions. Then it was pretensioned to 12 revolutions again and left over a period of 2 weeks.

The tests were carried out inside the laboratory to avoid direct solar radiation and maintain constant temperature.

Figure 3.11: Experimental test set-up

### 3.4.3 Results and discussion

Figure 3.12a shows the raw data, strain versus chainage for the blue connector when pretension is applied gradually (blue lines) and then decreased gradually (red lines). To avoid any influence of the clamping points, the data points between 4.5 m and 7.5 m were averaged to obtain the strain level in the pretensioned section of the fibre. The dataset 0 was used to baseline all measurements.

Figure 3.12b presents the baselined averaged strain measured with the BOTDR versus the strain measured by the LVDT. It can be seen that the data points for applying pretension are very close to the LVDT measurements and that the points for removing pretension are just slightly below. This indicates some plasticity, which is small enough to be neglected for this purpose. Strain versus clamps revolutions (Figure 3.12c) also yields a nearly linear relationship, up to a strain level of almost 6000 µε.

To investigate the ability of the clamps to keep a specific pretension, 17 hourly readings are taken on the 6th and 7th of June 2011 and 3 further readings taken on the 13th of June 2011. Except one reading, the 1st reading (taken directly after the BOTDR analyser was switched on) on the 13th of June, all

other readings are within a range of 50 µε (Figure 3.12d). This shows that the clamps can hold high pretensions of up to almost 6000 µε for more than one week. It also confirms that the warm-up reading is not reliable and shall be discarded.

Another test was carried out to investigate whether each fibre core in the same FO cable (there are four cores in each cable, Figure 3.5c\) gives the same strain measurement. Therefore two of the four cores were spliced to a connector, as described above. Figure 3.12e shows the measured strain taken from the blue and brown connector for dataset 6 . It can be seen that the two subsequent measurements from the same connector vary slightly and that the strain readings obtained from the brown connector are approximately 150 µε (0.015 %) larger than the ones from the blue connector; this was consistent in the other datasets. For future work it is therefore advised to make a note of the fibre colour which is spliced to the connector and to consistently use the same fibre in case re-splicing is necessary. This advice was followed throughout the Abbey Mills FO monitoring period.

(a) Raw strain versus chainage when gradually applying and removing pretension with clamps

Figure 3.12: Results pretension clamps laboratory test

(b) BOTDR strain versus LVDT strain

(c) BOTDR strain versus clamp revolutions

(d) Average strain versus time showing the ability of clamps to remain long-term pretension

(e) Readings taken at the same applied strain level from two different fibre cores of the same cable

Figure 3.12: (Cont.) Results pretension clamps laboratory test

## 3.5 Data acquisition

Before FO measurements could be taken, pigtails1 had to be spliced onto the ends of the FO cables to be able to connect them to the read-out units. The splicing process is very delicate and it was useful to have the protected data logging point, so that a higher quality of the splice could be achieved.

Table 3.2 gives an overview of the FO measurements that were recorded. A 'dataset' is a set of measurements taken on the same, or two subsequent days, at the same excavation level.

Data was collected twice before (datasets BD1 and BD2) and once during the dewatering trial (DD) that was carried out on the 1st and 2nd of February 2012. In the dewatering trial three wells were drilled inside the yet-to-beexcavated shaft, which are displayed in Figure 3.2. Wells W1 and W3 were used to lower the water level of the deeper aquifer from 24 to 70 mbgl (Figures 3.2 and 3.3c). No water was pumped from well W2; it was only used to measure the water level drawdown. The purpose of the dewatering trial was to test the groundwater cut-off of the diaphragm walls and the in situ permeability characteristics of the Chalk.

Further measurements were taken on nine different dates during shaft excavation between April and September 2012. After the completion of the excavation the base slab was constructed and an inner lining wall was erected. In April 2013 the annulus, which is the gap between the diaphragm wall and the inner lining, was filled with grout. Two datasets were taken; one before the annulus infill (BA) and one after (AA).

Two read-out units were used: the Yokogawa AQ8603 BOTDR (Yokogawa, 2005) and the Omnisens DITEST STA-R BOTDA (Omnisens SA, 2012). Further details can be found in Section 3.2. During the dewatering trial only the BOTDR was used. For the shaft excavation measurements the BOTDR was used for cables that had a breakage and the BOTDA was used for those without any breakages. Since the university-owned BOTDR read-out unit ('A' in Table 3.2) required maintenance, a replacement unit 'B' was used during the shaft excavation. Again, a different unit 'C' was used for the annulus infill datasets. It was found that the performance of different read-out units varies and therefore datasets taken with different read-out units should not be directly compared.

<sup>1</sup>pigtails are short FO cables with a plug on one side


| Dataset | Date        | Monitoring reason              | BOTDR         |
|---------|-------------|--------------------------------|---------------|
|         |             |                                | read-out unit |
| BD1     | 09/01/12    | 1st baseline before dewatering | A             |
| BD2     | 26/01/12    | 2nd baseline before dewatering | A             |
| DD      | 02/02/12    | during dewatering trial        | A             |
|         |             | Excavation-induced strain      |               |
|         |             | Exc depth [mbgl]               |               |
| E1      | 26+27/03/12 | 0                              | B             |
| E2      | 18+19/04/12 | 9                              | B             |
| E3      | 15+16/05/12 | 15                             | B             |
| E4      | 29/05/12    | 21                             | B             |
| E4rep   | 16/06/12    | 29                             | B             |
| E5      | 26/06/12    | 35                             | B             |
| E6      | 11/07/12    | 47                             | B             |
| E7      | 24+25/07/12 | 53                             | B             |
| E8      | 13/08/12    | 62                             | B             |
| E9      | 04/09/12    | 71                             | B             |
| BA      | 04/04/13    | Baseline for annulus infill    | C             |
| AA      | 17/04/13    | After annulus infill           | C             |

Table 3.2: FO datasets during different construction stages

## 3.6 Breakages and repairs

Unfortunately, not all FO cables remained intact without breakages. Several breakages were discovered in the strain-sensing fibre (Fujikura, 2009), but not in the more-robust temperature-sensing fibre (Mayflex Holdings Ltd., 2012). It has to be distinguished between (1) breakages that happened during installation of the FO cables and (2) breakages during shaft excavation.

During installation three breakages occurred. The BSC of panels P10 and P15 both broke towards the bottom of the wall. It is difficult to state a reason, as the breakage is covered in concrete and cannot be seen physically. The raw data of panel P10 showed a loss of pretension around the location of the breakage, which could indicate that the cable snapped. The HSC of P20 also showed a high level of noise at the location of a clamp which is most likely a large bend instead of a breakage. As panel P20 was the first one, for the following installations the loose cable on one side of the clamp was strengthened with wire (Figure 3.7f).

One breakage/ bend is acceptable and does not lead to loss of data, since the BOTDR can be used to interrogate the FO cable from both ends up to the breakage, so a full strain profile can still be obtained.

All of the breakages during shaft excavation were found at the BSC on the excavation face. The BSC was installed in the concrete cover closer to the wall/ soil interface; the HSC and TC, which were attached closely to the reinforcement bars, did not experience any damage. Figure 3.13 shows schematically how the breakages might have happened due to a combination of factors. In theory the BSC was installed with 48 mm concrete cover assuming its pretension would ensure the cable to remain with the same cover between the fixity points. In reality however the concrete aggregates and the vibration compaction could have pushed the cable closer to the wall/ soil interface between the fixity points, reducing the concrete cover to less than 48 mm. When then the excavator scraped the wall with its bucket and the wall was jet-washed to remove loose material, the theoretical concrete surface was reduced and the cable could easily be damaged (Figure 3.14a). For future installation it is suggested to fix the BSC every 2 to 3 m loosely with cable ties to the reinforcement, so it cannot be pushed closer to the wall/ soil interface.

This problem caused several breakages in panel P10 within the top 20 m of the wall. In panel P15 one breakage was discovered at the top of the wall. Panel P20 had one breakage just below capping beam.

In conclusion this means that the BSC of panels P10 and P15 had to be repaired, as both experienced more than one breakage. Without repair works a significant amount of data would have been lost.

A breakage of an optical fibre can be repaired by a fusion splice. This is a delicate procedure which is usually carried out in clean laboratory environment. To repair the breakages it was decided to by-pass the breakages with a robust cable as shown in Figure 3.15. This requires two splices to be carried out, one at the top of the wall and one at the lowest breakage where the cable comes out of the concrete. Especially the lower splice was difficult to accomplish, as it had to be carried out from a man-rider basket with a very short length of FO cable sticking out of the concrete (Figure 3.14b).

In panel P10 several breakages were visible over the excavation depth. The lowest visible breakage at approximately 20 mbgl was spliced to a piece of additional cable, which was again spliced to the existing cable at the top of the wall to by-pass the breakages (Figure 3.15a). In panel P15 the measurements showed a breakage just below capping beam which was not visible when inspecting the wall. Therefore the cable was cut at approximately 7 mbgl depth where it was exposed. Again a piece of additional cable was used to by-pass the breakage (Figure 3.15b). The spliced sections were protected inside a waterproof box (Figures 3.14c and 3.14d).

After the repair works new baseline readings were taken. For panel P15 the new baseline was taken along with other readings on the 29th of May 2012 (E4, 21 mbgl, Table 3.2). At panel P10 the repair works were more complicated and baseline readings were only taken on the 15th of June 2012 (E4^rep^, 29 mbgl, Table 3.2).

Figure 3.13: Longitudinal section through panel with arrangements of FO cables and detail of concrete cover at different locations

(a) Breakage at panel P10 and rough concrete surface

(b) Carrying out the splice close to the wall with short cable length from man-rider basket

(c) Waterproof splice protection box fixed to wall

(d) Splice at top of wall

Figure 3.14: Repair works in pictures (Courtesy of Thames Water)

Figure 3.15: Repair works to by-pass breakages

## 3.7 Data analysis

The FO read-out unit provides absolute strain profiles along the length of the cable. Several analysis steps are necessary to process the raw data into the required information. Figure 3.16 gives a schematic overview of the steps.

The subsections below firstly introduce the principle of temperature compensation and then detail how the curvature, the bending moment and the hoop strain are obtained.

### 3.7.1 Principle of the temperature compensation

As mentioned in Section 3.2 the Brillouin peak frequency shift is linearly dependent on temperature-induced and mechanical strain. Equation 3.5 related the measured shift in Brillouin peak frequency ∆*ν*<sup>B</sup> to the combined (temperature-induced and mechanical) strain *ε*comb. To enable the isolation of the mechanical strain, a loose tube FO cable (Figure 3.5d\), the TC, was installed in the diaphragm wall as shown in Figure 3.6a. The combined strain profiles were subtracted from a baseline reading to obtain the incremental strain profiles of the BSC and HSC, the incremental combined strain ∆*ε*comb. The incremental temperature-induced strain from the TC ∆*ε*<sup>t</sup> is multiplied by a factor *α*<sup>t</sup> and then subtracted from ∆*ε*comb to isolate the incremental mechanical strain ∆*ε* as given in Equation 3.6.

$$\Delta \varepsilon = \Delta \varepsilon_{\text{comb}} - \alpha_{\text{t}} \cdot \Delta \varepsilon_{\text{t}} \tag{3.6}$$

The factor *α*<sup>t</sup> is necessary to transfer the temperature strain measured with the loose tube cable to the Fujikura reinforced cable, which have different thermal expansion coefficients and embedment conditions. Mohamad \(2008\) detailed this in his thesis. He derived the following formula to relate change in temperature ∆*T* to change in measured strain ∆*ε*<sup>t</sup> ,

$$\Delta \varepsilon_{\mathsf{t}} = (\alpha_{\mathsf{a}} + \alpha_{\mathsf{n}}) \cdot \Delta T \tag{3.7}$$

where *α*<sup>a</sup> is called the temperature-induced apparent or intrinsic strain and is constant at 19.47 µε/K for all optical fibres; *α*<sup>n</sup> is the net thermal expansion of the jacketed fibre and is different for each FO cable. Mohamad \(2008\) determined these values experimentally to 4.2 µε/K for the loose tube cable and 23.2 µε/K

Figure 3.16: Schematic overview of FO data analysis

#### Fibre optic instrumentation

for the Fujikura reinforced cable. The experiments were conducted in a water bath, i.e. assuming that the fibre is not embedded. For the loose tube cable this is appropriate, as the fibres swim in a gel and no strain is transferred from the concrete. For the Fujikura cable this assumption is not appropriate, as it is embedded in concrete. Therefore the thermal expansion of the concrete dominates and *α*<sup>n</sup> is replaced by 10 µε/K, the thermal expansion coefficient for concrete. Hence, *α*<sup>t</sup> is determined as follows,

$$\alpha_{\rm t} = \frac{\alpha_{\rm a} + 10\,\mu\epsilon/K}{\alpha_{\rm a} + 4.2\,\mu\epsilon/K} = 1.25. \tag{3.8}$$

### 3.7.2 Data analysis step by step

#### 3.7.2.1 General steps

The loop arrangement of the BSC (Figure 3.6\) enables the computation of curvature and bending moment, while the HSC cable allows the measurement of circumferential strain (Figure 3.6\). Several steps have to be carried out to extract this information from the raw data.

**Average readings of each dataset:** On each site visit three readings per FO cable were taken. These three readings were averaged so that one strain profile per dataset is obtained. Figure 3.17 shows the averaged datasets of the BSC, TC and HSC.

**Interpolation and auto-correlation:** It is very common that the cable length changes throughout the monitoring period. This may be related to the use of extension cables or splices that were carried out. An example is displayed in Figure 3.18a where a new splice caused an offset between the datasets. Smaller offsets can also be caused by inaccuracies of the distance measurement of the read-out unit. Even small offsets can induce errors; this is especially crucial for the BSC and HSC due to the peaks and valleys in the raw data (Figures 3.17a and 3.17c\). To correct for these potential offsets the datasets were correlated. Therefore the data was first interpolated from a data point every 0.1 m to 0.01 m to be able to make finer adjustments. After the interpolation an auto-correlation algorithm was run on the BSC and HSC. The algorithm sums up the squared difference between each dataset and a reference dataset and then shifts the datasets according to the value of the minimum squared difference. Figure 3.18b shows the correlated data. For the TC the correlation was done manually, as the auto-correlation algorithm cannot be used (due to missing peaks and valleys, Figure 3.17b\) and small offsets do not induce inaccuracies.

**Repeatability:** The BOTDR read-out unit has a quoted repeatability of ±400 µε \(Yokogawa, 2005\), which means that datasets may be shifted by this amount. For the TC all datasets were shifted to 0 strain in the bottom loop (Figure 3.17b\), assuming that temperature at the bottom of the wall remains constant. If the BSC cable is not broken, the repeatability compensates automatically when the difference between the excavation and soil side strain is taken and this step is not required. If the cable is broken, the repeatability compensation is not possible, as one part of the data does not include a bottom loop. Hence it was omitted completely. For the HSC a repeatability compensation should be done, but due to the arrangement of the bottom loop, accidentally in circumferential direction, this was also not possible and was omitted.

**Filter:** The strain profiles from the TC taken with the BOTDR were noisy and required filtering; the filtered data of panel P20 is shown in Figure 3.17b. Since the strain profiles are smooth, this does not induce a significant error. If filtering was done on the strain cables (BSC and HSC), this might induce errors due to the peaks and valleys in the strain profiles.

**Stitch:** As mentioned before, some BSC have experienced breakages. With less than one breakage data can be obtained from both ends of the cable up to the breakage point. During the analysis the data from both ends had to be 'stitched' together.

**Differential strain:** The absolute measured strain shows the initial applied pretension and the strain induced by concrete curing; hence it does not have any significant meaning. The incremental strain on the other hand indicates changes in strain between a dataset and a reference reading. Therefore all datasets are subtracted from a baseline reading to obtain differential strain.

(a) BSC of panel P20 taken from soil face cable side (averaged, interpolated, correlated)

(b) TC of panel P20 taken from soil face cable side (averaged, interpolated, correlated, repeatability compensated, filtered)

(c) HSC of panel P10 taken from excavation face cable side (averaged, interpolated, correlated)

Figure 3.17: Strain versus chainage

(a) Before auto-correlation: New splice was carried out between datasets 21 mbgl and 35 mbgl which caused an offset of approximately 0.5 m

(b) After auto-correlation: Peaks and valleys of all datasets match well

Figure 3.18: Interpolation and auto-correlation of datasets

#### 3.7.2.2 Steps specific to bending strain analysis

**Extract strain:** The measurements provide a distributed strain profile along the cable, also including sections outside the wall and the bottom loop, which are not required for the analysis. Therefore the relevant sections were extracted, which are the vertical sections on the soil and excavation face between the pretension points (Figure 3.6\). For the BSC these can be easily identified, as the relevant sections are pretensioned and feature higher absolute strain values (Figure 3.17a\). For the TC the 10 m bottom loop position is recognisable and since TC runs in parallel to the BSC the relevant sections can easily be determined.

**Temperature compensation:** Having extracted and thereby aligned the soil and excavation face data from the BSC and TC, the temperature compensation according to Section 3.7.1 can be carried out.

**Calculate curvature:** Assuming linear-elastic material behaviour, the curvature ∆*κ*Y−<sup>0</sup> between the dataset *Y* and the baseline dataset 0 can then be calculated according to Equation 3.9,

$$\Delta \kappa_{Y-0} = \frac{\Delta \varepsilon_{s} - \Delta \varepsilon_{e}}{A} \tag{3.9}$$

where ∆*ε*<sup>s</sup> and ∆*ε*<sup>e</sup> are the temperature compensated incremental strains on the soil and excavation face respectively and *A* is the distance between the soil and excavation face cable (Figure 3.19\).

Figure 3.19: Calculation of curvature

**Calculate bending moment:** The elastic law then relates curvature to bending moment by multiplication with the wall's flexural stiffness *EI*,

$$\Delta B M_{Y-0} = \Delta \kappa_{Y-0} \cdot EI \tag{3.10}$$

**Lateral wall movement:** Theoretically the lateral wall movement can be derived from the curvature. Through the first integration over the depth of the wall the incremental inclination angle ∆*α*<sup>i</sup> can be obtained,

$$\Delta \alpha_{\rm i} = \int_{H_{\rm d}}^{0} (\Delta \kappa + C_1) dz \tag{3.11}$$

through the second integration the lateral wall movement, ∆*u*, is obtained,

$$\Delta u = \int_{H_{\rm d}}^{0} (\Delta \alpha_{\rm i} + C_2) dz \tag{3.12}$$

where *H*<sup>d</sup> is the depth of the diaphragm wall and *C*<sup>1</sup> and *C*<sup>2</sup> are the integrations constants. The constants are usually assumed to be 0, i.e. the bottom of the wall is fixed (no rotation and no lateral movement).

#### 3.7.2.3 Steps specific to hoop strain analysis

**Average peak strain:** From the raw data (Figure 3.17c\) the location of the pretensioned peaks can easily be recognised. A close up view of one of these peaks is provided in Figure 3.20, showing strain versus chainage for different excavation levels. At the top of the figure the strain initially induced in the cable with the pretension clamps is shown. Even though the induced strain profile is a step change (dashed black line), the measurement data gives smooth curves. This is due to the 1 m spatial resolution of the BOTDR analyser, which means that the strain measurements are averaged over 1 m. Hence, the real strain in the pretensioned section is only reflected by the centre part which is more than 0.5 m away from the pretension points; here it is picked to be 250 mm wide. The differential strain between the datasets and the baseline was averaged over this central interval. This yields the hoop strain without temperature correction, ∆*ε*θ,comb (one value for each of the eight peaks).

**Temperature compensation:** The final step is the temperature compensation. Since the pretensioned peaks are concentrated in a 10 m section, the average temperature of the TC, separate for soil and excavation face, can be extracted from the TC, ∆*ε*soil,t and ∆*ε*exc,t. According to Equation 3.6 the temperature compensation is carried out, to yield the mechanical hoop strain ∆*ε*<sup>θ</sup> (again one value for each of the eight peaks). It can then be plotted versus time or excavation depth.

Figure 3.20: Close up view of one pretensioned section of the HSC

# Chapter 4

## Conventional instrumentation

## 4.1 Overview

Apart from the fibre optic (FO) instrumentation detailed in Chapter 3, conventional instruments, including inclinometers, extensometers and optical targets, were installed at Abbey Mills. Inclinometers typically measure horizontal soil or wall movement, while extensometers provide settlement and heave.

A plan view of the inclinometer and extensometer boreholes is provided in Figure 3.2; two arrays of boreholes radiate from the shaft (array A behind panel P15 and array B behind panel P20). A close up plan view of one array is shown in Figure 4.1a. Each array consists of one manual inclinometer in the shaft wall (I1), three manual inclinometers in 6, 15 and 30 m distance from the shaft wall (I2, I3 and I4), two automatic rod extensometers 2.5 and 6 m from the shaft (E1 and E2) and two manual magnet extensometers in 15 and 30 m distance (E3 and E4). The boreholes in 15 and 30 m distance can be used for both the manual inclinometer and extensometer. Initially the boreholes I2 were instrumented with automatic in-place inclinometers. However, due to unrealistically large movements measured before excavation started, it was decided to remove them and carry out a manual inclinometers survey as for the other boreholes.

Figure 4.1b provides a cross-sectional view of the boreholes of one array showing their depths and the anchor locations of the multi-point extensometers. The installation as well as the data acquisition were carried out by the subcontractor SolData Ltd.

The contractor, JV MVB (Joint venture Morgan Sindall, Vinci Construction Grands Projets and Bachy Soletanche), carried out two optical surveys to monitor the surface settlement and the diaphragm wall movement.

As shown in Figure 3.3a the soil inclinometers and extensometers were in place before the diaphragm wall construction from September 2011 until June 2013; wall inclinometer readings commenced with shaft excavation in April 2012; the optical surveys were conducted during shaft excavation. The automatic rod extensometers took a measurement every 5 minutes. All other conventional instruments were interrogated manually, approximately once or twice a week.

## 4.2 Extensometers

### 4.2.1 Automatic rod extensometers

As shown in Figure 4.1a, each of the two arrays A and B consists of two boreholes for automatic rod extensometers, E1 and E2, 2.5 and 6 m away from the shaft wall. Each rod contains six multi-point Borros type anchors which are connected to the reference head where the measurements are recorded with vibrating wire technology. Figure 4.1b shows the specified depths of the anchors in relation to the soil stratigraphy; these may differ slightly from the final installed locations. For some anchors it was planned to place them above or below critical layers, such as the highly compressible Alluvium or the Calcrete. Since the layers are thin and the stratigraphy varies slightly, this might not always have worked out as planned.

A schematic view of one of the rod extensometer boreholes is shown in Figure 4.2a. The hydraulic anchors at various depths are connected to the vibrating wire sensors in the reference head (Figure 4.2c\); the connection rods between head and anchor are protected by a hollow pipe. After installation the borehole is backfilled with grout.

The reference head was supported by a sandy backfill, but was essentially free to move (Figure 4.2c\). Therefore a borehole head survey was carried out which was supposed to act as reference. However this survey yielded very noisy results and could not be used as a reference point. Therefore the lowest anchor which extends into the Chalk group was considered to be stable and was used as reference. The baselined vertical movement of each anchor ∆*L* ∗ is obtained by subtracting the change in vertical position of each anchor ∆*L* and the reference ∆*L*ref (deepest anchor),

$$\Delta L^* = \Delta L - \Delta L_{\text{ref}} \tag{4.1}$$

Figure 4.1: Overview and location of boreholes for inclinometers and extensometers in one array (A or B)


- (a) Schematic view of automatic rod extensometer borehole
- (b) Schematic view of borehole for manual extensometer and inclinometer

(c) Reference head of rod extensometer during installation (Courtesy of Thames Water)

(d) Fotograph of spider magnet which is attached around an inclinometer casing ([http://www.mgs.co.](http://www.mgs.co.uk/) [uk/](http://www.mgs.co.uk/))

(e) Interrogating the manual extensometers with measurement tape (Courtesy of Thames Water)

(f) Cross-section of inclinometer casing

(g) Metric inclinometer probe used at Abbey Mills

Figure 4.2: Inclinometers and extensometers at Abbey Mills site

The major advantage of automatic in-place sensors is the high monitoring frequency, which was set to 5 minutes at Abbey Mills. Monitoring started in September 2011 when the diaphragm walls were being constructed and continued until June 2013.

### 4.2.2 Manual magnet extensometers

In addition to the automatic extensometers each array has two manual magnet extensometers, E3 and E4, in 15 and 30 m distance from the shaft wall. The magnets are attached around an inclinometer casing (Figures 4.2b and 4.2d\), which allows the borehole to be used for both, magnet extensometer and manual inclinometer. Each borehole has between 4 to 6 spider magnets over its depth, the positions are shown in Figure 4.1b.

To take a measurement a probe on a steel measuring tape is lowered into the borehole. When passing the magnet sensor the probe beeps; then the technician reads the number from the measuring tape at the borehole head, which acts as datum (Figure 4.2e\). This procedure is followed for each spider magnet. The differential movement can then be calculated by subtracting the noted numbers from the baseline reading. The steel measuring tape has cm-marks (Figure 4.2e\); reading the number of the tape at the height of the datum can probably be done with an accuracy of ±10 mm, also considering that the technician wears gloves and that the borehole head is approximately 0.5 m deep inside a manhole (Figure 4.2e\).

## 4.3 Inclinometers

### 4.3.1 Overview, terminology and data analysis

Each array A and B consists of four manual inclinometers (Figures 3.2 and 4.1\) one of which is in the shaft wall and three of which are 6, 15 and 30 m behind the shaft wall. A third shaft inclinometer is in panel P10 (Figure 3.2\).

An inclinometer casing has four grooves which are orientated in 90° of each other (Figure 4.2f\). The A-axis points towards the centre of the shaft and the B-axis in tangential direction. For each survey the inclinometer probe, as shown in Figure 4.2g, is inserted so that the wheels are in the A-axis grooves, with the upper wheel pointing towards the shaft. After the pass is completed the probe is rotated by 180°, now the upper wheel is facing away from the shaft, and again lowered into the borehole.

Taking a 0° and a 180° reading is important to cancel out the probe's bias, which can shift throughout the probe's lifetime. The bias is the non-zero value measured by the probe even though it is absolutely vertical (Figure 4.3b\). To cancel any bias shifts between two surveys the 0° and the 180° readings are averaged.

The inclinometer probe used at Abbey Mills site was a biaxial probe which also measured the inclination in the B-axis direction while the wheels travelled in the A-axis grooves. In comparison to a uniaxial probe, which requires to take 90° and 270° readings as well, the biaxial probe saves time. The disadvantage however is the decrease in accuracy. Since the grooves are slightly wider than the wheels, the probe might 'wobble' and therefore cause inaccurate readings in the B-axis.

Each pass of the probe starts from the bottom of the borehole. After 10 minutes to allow for temperature adjustment of the probe, it is pulled up in intervals of 0.5 m. An instrument reading for each interval *i* is recorded, *A*0(*i*) or *A*180(*i*), depending on whether it is the 0° or the 180° pass. This data can be processed into the required information, which is usually the lateral wall movement. The inclinometer data can also be used to compute the curvature of the wall, which is useful to compare with the FO data. Several steps are necessary and outlined below according to Figure 4.3a:

**Combined reading & checksum:** The raw data *A*0 and *A*180 are averaged to cancel the bias, which may occur between two surveys, and obtain the combined reading *A*comb,

$$A_{\rm comb} = \frac{(A0 - A180)}{2} \tag{4.2}$$

*A*0 and *A*180 can be added to obtain the checksum *Acheck*, which isolates the bias and can give indications about potential errors,

$$A_{\text{check}} = \frac{(A0 + A180)}{2} \tag{4.3}$$

**Correct for depth position error (DPE):** This step is optional and only required if the data is erroneous. Further details on error correction are given in Section 4.3.2.

**Angle of tilt:** The sine of the angle of tilt *θ* is obtained by dividing the combined

reading  $A_{comb}$  by the instrument constant k,

$$\sin \theta = \frac{A_{\text{comb}}}{k} \tag{4.4}$$

**Deviation:** Multiplying the sine of the angle of tilt with the measurement interval (= 500 mm) yields the deviation  $d_e$  of each interval (Figure 4.3c),

$$d_e = \sin\theta \cdot 500 \tag{4.5}$$

**Integration (casing shape):** Having obtained the deviation of each 500 mm interval, these values can be added up from a known boundary condition. A head survey was carried out, but the data was too noisy to be used. Therefore the bottom of the borehole was assumed fixed. The so-called cumulative deviation profile  $u_{\rm cumdev}(z)$ , which is the inclinometer casing shape, is calculated as follows,

$$u_{\text{cumdev}}(z) = \sum_{i=1}^{i_{\text{max}}} d_{e}(i) \tag{4.6}$$

where i is counting from inclinometer interval 1 at the bottom of the borehole to inclinometer interval  $i_{max}$  at the top of the casing. This is also illustrated in Figure 4.3d.

**Baseline:** The casing shape is of no significance, but the change of shape is. To obtain the lateral movement, the data has to be baselined with the initial survey,

$$\Delta u(z) = u_{\text{cumdev}}(z) - u_{\text{cumdev,base}}(z) \tag{4.7}$$

If no bias error occurred, this is the required lateral movement  $\Delta u(z)$ .

**Bias correction:** If bias error occurred, it has to be corrected at this stage. Further details are given in Section 4.3.2.

**Baseline angle of tilt:** To derive the curvature from the inclinometer measurements, the angle of tilt is baselined,

$$\Delta \theta = \theta - \theta_{\text{base}} \tag{4.8}$$

**Interpolate & filter:** The probe only takes one measurement every 500 mm. For the differentiation in the next step this is not sufficient. Therefore the  $\Delta\theta$  profiles are firstly interpolated to 10 mm resolution and then filtered.

**Differentiate:** The  $\Delta\theta$  profiles are then differentiated with respect to depth z to obtain the curvature,

$$\Delta \kappa_{=} \frac{\delta \Delta \theta(z)}{\delta z} \tag{4.9}$$

Figure 4.3: Inclinometer data analysis

(b) Converting from instrument reading to slope from vertical and instrument bias

Figure 4.3: (Cont.) Inclinometer data analysis

### 4.3.2 Accuracy and errors

Establishing the accuracy of an inclinometer is not straight forward. Errors in lateral movement accumulate with depth and can be significant for deep boreholes like those at Abbey Mills. In addition, it has to be distinguished between random and systematic errors which can be difficult.

The manufacturer of the inclinometers \(Slope Indicator, 2011a\) quotes an accuracy of ±6 mm per 50 gauge lengths. With a metric probe (gauge length = 500 mm) this corresponds to a 25 m deep borehole. According to Mikkelsen \(2003\) these quotations are conservative and the total error *TE* is an aggregate of random errors *RE* and systematic errors *SE*. For a 50 m deep borehole which has 100 intervals the accuracy can be calculated as follows,

$$TE = RE + SE = \pm 0.16 \cdot \sqrt{100} \pm 0.11 \cdot 100 = \pm 1.6 \pm 11 = \pm 12.6 \text{mm} \tag{4.10}$$

where ±0.16 mm is the random error for a single reading and ±0.11 mm is the assumption for the systematic error of a single reading. The smaller random error (±1.6 mm) cannot be corrected. The larger systematic error (±11 mm) is a combination of the following: Sensor bias shift, sensitivity drift, sensor alignment shift (rotation), DPE, casing inclination and curvature; correction may be possible.

**Sensor bias shift** is the most common error \(Mikkelsen, 2003; Slope Indicator, 2009\). If a shift in the probe's bias (Figure 4.3b\) occurs between the 0° and the 180° pass, the derived lateral movement profile may be rotated around the fixity point. This can be corrected if, apart from the bottom of the borehole, another point of zero movement is known. Therefore it is usually recommended to extend the boreholes 3 to 6 m into ground that is considered stable \(Slope Indicator, 2009\).

**Sensitivity drift** is not very common, but can occur if the instrument constant shifts. Factory calibration can reveal this problem \(Mikkelsen, 2003\). It is however difficult to correct, as the exact value of the sensitivity drift for each dataset is unknown.

**Rotation error** can occur if the alignment of the sensor axis relative to the initial survey changes and if the inclinometer casing is installed with large inclination in the perpendicular axis.

**DPE** is another error which most likely occurred on this site. The surveys are prone to this error when the casing has been installed in S- and/or J-shape, in combination with anything that changes the position of the probe in the casing, such as change of top reference point, change of cable or settlement around the inclinometer casing.

Figure 4.4 schematically explains how DPE occurs. Three surveys are carried out where the inclinometer probe positions of surveys 2 and 3 are lower and higher respectively than in the baseline survey 1. In survey 2 the probe takes larger inclination readings; in survey 3 smaller readings. The data analysis procedure assumes that the measurement depths of surveys 2 and 3 are the same as the baseline survey 1, and the subtraction of the cumulative displacement profiles in Equation 4.7 hence results in erroneous lateral displacement profiles.

The error is easy to identify, but the correction process is elaborate and time-consuming if the exact value of depth error is not known. Through error and trial a suitable depth error value can be approximated and used to correct the data \(Mikkelsen, 2003; Slope Indicator, 2009\).

**Groove spiral error** can occur if the casing is installed with a large spiral twist. These values usually have to exceed 15° to make a difference to the measurements \(Slope Indicator, 2002\).

Figure 4.4: Example of DPE occurrence in J-shaped casing caused by different positions of the probe - reproduced from Mikkelsen \(2003\)

### 4.3.3 Error correction

#### 4.3.3.1 Uncorrected lateral movement

The error correction procedure is exemplified for one inclinometer, AI3, which is 15 m away from the shaft wall behind panel P15 (Figures 3.2 and 4.1\). The uncorrected data is shown in Figure 4.5a; the lateral displacement profiles at different excavation depths exhibit several abnormalities: (1) movement does not develop gradually but erratic, (2) displacement occurs far below excavation level and (3) profiles feature wavy and pointy shapes. The 9 mbgl survey in Figure 4.5a (light blue) for example suggests that movements occurred at depths far below the excavation level, which seems unreasonable.

#### 4.3.3.2 Depth position error

The wavy and pointy shapes at specific depths lead to the assumption that DPE may have occurred. DPE is a common error if the inclinometer casing shape is not straight but S- and/or J-shaped. When examining the casing shape of AI3 (Figure 4.6a\), which is obtained by integrating the deviation measurement of the initial survey (Figure 4.6b and Equation 4.6\), these features can be found. One of the erroneous measurements, the 9 mbgl survey, is further investigated for this demonstration. If the erroneous lateral displacement profile (black line in Figure 4.6c\) is compared to the deviation profile (Figure 4.6b\), it is obvious that some patterns match well: Spikes and curves in Figure 4.6b correspond to the curves and peaks in the lateral movement profile.

This error can be corrected easily if the amount of depth offset of the probe *d*DPE is known. The corrected combined reading of a specific interval *A* cor comb(*i*) is obtained as follows,

$$A_{\text{comb}}^{\text{cor}}(i) = A_{\text{comb}}(i) + (A_{\text{comb}}(i \pm 1) - A_{\text{comb}}(i)) \cdot \frac{|d_{\text{DPE}}|}{500 \,\text{mm}} \tag{4.11}$$

where *A*comb(*i*) is the combined reading obtained from Equation 4.2. If the probe's position is lower than in the initial survey, the reading below *A*comb(*i* − 1), if the position is higher, the reading above *A*comb(*i* + 1) is used in the equation. The result *A* cor comb replaces *A*comb in Equation 4.4.

At Abbey Mills site the depth error value is unfortunately not known and a value had to be assumed. For each survey several *d*DPE values were tried, as exemplary shown for the 9 mbgl survey in Figure 4.6c, where the coloured lines

represent the lateral displacement profiles for different *d*DPE values between -50 mm and 50 mm. Then the *d*DPE value that gave the most reasonable shape was picked. 'The most reasonable shape' in this example would be between -40 mm and -50 mm as this removes the curvy and pointy shapes at deep depths which is not expected at a shallow excavation depth.

Firstly, constant *d*DPE values were considered. This removed the curves and peaks towards the bottom of the inclinometer, but induced a more wavy pattern at the top. Better results were obtained with linear *d*DPE where the maximum *d*DPE value is at the bottom of the casing linearly decreasing to zero at the top.

The DPE-corrected lateral movement profiles for all excavation levels are shown in Figure 4.5b. The shape has significantly improved when comparing to the uncorrected data (Figure 4.5a\).

#### 4.3.3.3 Bias error

After having corrected the curvy and pointy shape, the problem of the erratic movement can be tackled. Since the profiles feature random rotations (around the bottom fixity point) the common bias error appears to have occurred. Bias error can be corrected easily if a section of the inclinometer casing is in stable ground. Then another depth of zero movement (apart from the bottom of the inclinometer casing) *z*fix is known. The corresponding 500 mm measurement interval is *i*fix at which the bias-corrected lateral movement ∆*u*bias(*i*fix) = 0. Equation 4.12 essentially rotates the profiles around the bottom fixity to ensure ∆*u*bias(*i*fix) = 0.

$$\Delta u_{\text{bias}}(i) = \Delta u(i) - i \cdot \frac{\Delta u(i_{\text{fix}})}{i_{\text{fix}}} \tag{4.12}$$

At Abbey Mills the casings did not extend into stable ground, in fact most boreholes are shallower than the maximum excavation depth (Figure 4.1b\). For shallow excavation levels it is feasible to assume a fixity point below the excavation level; however due to the presence of DPE care has to be taken. If the 2nd fixity point is picked at a depth that is prone to DPE (e.g. 42 mbgl in Figure 4.6c\), the assumed *d*DPE value significantly affects the results. Hence, the location of the 2nd fixity point should be picked at a depth with small DPE influence. For AI3 the fixity point was picked at 32.5 mbgl, as this is the deepest reliable point (Figures 4.5c and 4.6c\). This seems to be a reasonable assumption for the surveys at 9, 15, 21, 35 and even for 47 mbgl when considering that the inclinometer location is 15 m away from the shaft. The 53 mbgl survey

Figure 4.5: Lateral movement over depth for inclinometer borehole AI3

Figure 4.6: Identifying DPE for inclinometer borehole AI3

was fixed at 40 m, which is not ideal as it has a larger DPE influence, but it is the only option. The surveys after 53 mbgl do not allow to pick a stable fixity point anymore and are therefore not bias corrected. Hence this data shall be considered with care and is marked with an attention symbol in the legend in Figure 4.5c.

For the shaft inclinometers it is also difficult to pick a 2nd fixity point for deeper excavation levels, but here it is possible to assume that the movement at the top of the wall is restrained due to the capping beam. Figure 4.7 explains how the bias correction is conducted. The 62 mbgl dataset is displayed which was bias-corrected as detailed above by picking a 2nd fixity point below excavation level. For the 71 mbgl dataset this is not possible anymore and here it is assumed that the top of the wall does not undergo significant movement and remains at the same deflection value, i.e. ∆*u*71mbgl(*z* = 0) = ∆*u*62mbgl(*z* = 0). The 2nd fixity point *z*fix for the 71 mbgl dataset is picked towards the top of the wall as well, as shown in Figure 4.7. The lateral deflection is not fixed at zero, but at the value of the previous dataset, i.e. ∆*u*71mbgl(*z*fix) = ∆*u*62mbgl(*z*fix). The profile is then rotated around the top fixity point onto the 2nd fixity point. This procedure is very sensitive to the fixity points and hence the data is less reliable.

Figure 4.7: Principle of boundary condition and bias shift correction for shaft inclinometer readings taken at deeper excavation levels

## 4.4 Levelling pins

Around Abbey Mills shaft eight levelling pins in the concrete platform were surveyed by the contractor JV MVB. As shown in Figure 3.2 the targets are arranged in two arrays each consisting of four individual targets (Array southwest/ northeast: targets 6000-6003, Array northwest/ southeast: targets 6100-6103). The targets are road nails drilled and glued into a surface feature.

The closed loop levelling survey requires at least two stable benchmarks. At Abbey Mills site three benchmarks existed; they were targets on concrete light towers 63 m north, 128 m south and 152 m north-west of the centre of the shaft, which is outside the expected zone of influence. They were periodically checked to ensure no movement had occurred.

The survey was carried out with a precise level (Leica DNA03), which specifies an accuracy of 0.3 mm per measurement (Leica Geosystems AG, 2013a). Using a starting and ending benchmark allows the calculation of the misclosure of the loop. If the misclosure is larger than 2 mm the survey will be repeated. It is usually around 0.5 mm; this value is then equally distributed between all surveyed points. Further errors can be caused by air temperature and seasonal variations. All together, this usually results in an accuracy of approximately ±1 mm.

The survey started on the 25th of May 2012 when the excavation had proceeded to almost 20 mbgl, which is taken as baseline. Readings were then taken every 4 days on average.

## 4.5 Diaphragm wall survey

The contractor JV MVB also surveyed the diaphragm wall. Several targets (Figure 4.8a) were attached to the diaphragm wall. Figure 4.8b provides a schematic overview of the arrangement of those targets; the targets' location in plan view is shown in Figure 3.2. The targets of array 1 were fixed at capping beam level (0 mbgl) and several further arrays were put in place at 12 mbgl (array 2), 31 mbgl (array 3), 46 mbgl (array 4) and at 61 mbgl (array 5).

The targets of the capping beam array could be placed on the 5th of April 2012, a few days after excavation started. All other targets in the non-capping beam arrays have the disadvantage that they could only be installed and surveyed after the excavation exposed this particular level. This means that the

wall had already undergone movement before the targets were placed, which cannot be quantified.

The survey was carried out with a total station. Firstly for each monitoring round, the capping beam targets were surveyed. Therefore the total station was set up on the ground surface around the shaft. Using a minimum of four reference points, the three-dimensional coordinates of the capping beam targets can be determined by the resection technique. The reference targets (Figure 4.8a) were installed outside the zone of expected movement and were periodically checked to ensure they remained stable. After having monitored the capping beam targets, the surveyor set up the total station inside the shaft at excavation level to take measurements of the non-capping beam targets. For this, the capping beam targets acted as reference and their values were held as fixed stable points.

The Leica TPS1201+ total station has an accuracy of 1 arcsecond for angle measurement and ±1 mm for distance measurement (Leica Geosystems AG, 2013b). At Abbey Mills this resulted in an accuracy of approximately ±2 mm for the capping beam targets in position and level. For the non-capping beam targets the errors accumulated to approximately ±4 mm.

After correspondence with JV MVB's surveying department it was found that a Project Control network adjustment was carried out on the 8th of July 2012. This amended the base control site coordinates by approximately 3 mm in both northing and easing, but did not affect the level coordinates. To incorporate this in the graphs a new baseline was set on the 10th of July (i.e. the movement on the 10th was set equal to the values from the 5th of July 2012).

The Leica TPS1201+ provides three-dimensional coordinates (easting, northing and level). From these coordinates the differential movements of the target ∆*E*, ∆*N* and ∆*V* between two dates can be obtained. However, for the analysis it is more useful to know a panel's movement towards the centre of the excavation ∆*S* and tangential to the wall ∆*T* (Figure 4.8c\). Hence ∆*E* and ∆*N* are converted as follows,

$$\begin{bmatrix} \Delta S \\ \Delta T \end{bmatrix} = \begin{bmatrix} -\sin(\phi_{d}) & -\cos(\phi_{d}) \\ -\cos(\phi_{d}) & \sin(\phi_{d}) \end{bmatrix} \cdot \begin{bmatrix} \Delta E \\ \Delta N \end{bmatrix} \tag{4.13}$$

where *φ*<sup>d</sup> is the rotation angle as shown in Figure 4.8c. ∆*S* is positive for movement towards the centre of the shaft; ∆*T* for anticlockwise movement.

(a) Photograph of a target inside the shaft (Courtesy of Thames Water)

(b) Eight targets at the same level constitute one array; targets at different levels in same plan location constitute one string and opposite targets in each array are used to obtain convergence

(c) Converstion from eastings and northings into components towards shaft centre and tangential to the shaft wall

Figure 4.8: Optical diaphragm wall survey

# Chapter 5

### Monitoring results

## 5.1 Introduction

Chapters 3 and 4 detailed the monitoring instrumentation put in place at Abbey Mills. This Chapter presents the results in comparison with the PLAXIS design predictions.

The PLAXIS design is summarised in Section 5.2. The main motivation for the instrumentation was the monitoring during the shaft excavation between April and September 2012 (Figure 3.3a); the results from the fibre optic (FO) and conventional instrumentation are presented in Section 5.3. During the diaphragm wall construction between September and December 2011 inclinometer and extensometer measurements were taken; those are presented in Section 5.4. Monitoring results are also obtained for several further construction stages, such as the dewatering trial in February 2012 (Section 5.5) and the annulus infill in April 2012 (Section 5.6).

## 5.2 PLAXIS design

The initial design of the Abbey Mills shaft was conducted with the finite element (FE) modelling software package PLAXIS version 9.0 (Brinkgreve et al., 2009) which was run in two-dimensional axisymmetric mode. The work was carried out by Bachy Soletanche and this thesis uses their results for comparisons with the field data.

A Mohr-Coulomb (MC) soil model without strain hardening was adopted for all layers: Made Ground, River Terrace Deposits, London Clay, Lambeth Group Clay, Lambeth Group Sand, Thanet Sand and Chalk. The thinner layers, i.e. the Harwich Formation and the Calcrete are not explicitly modelled. The input properties are shown in Table 5.1 which are characteristic design values to which a partial safety factor of 1.0 was applied for the serviceability limit state (SLS) (British Standards Institution, 2004b).

The Geotechnical Interpretative Report (GIR) (Morgan Sindall, 2012) details how the parameters were derived. They are mostly based on standard penetration tests, laboratory investigations and correlations with published data. For the Thanet Sand and the unweathered medium to hard, rubbly to blocky Chalk (Clayton, 1990) in situ high pressure dilatometer tests at different strain levels were conducted and the Young's moduli were picked at an axial strain level of 0.1%.

Installation effects were not directly modelled, but incorporated by reduced lateral earth pressure coefficients $K_0$ of the London Clay and the Lambeth Group (both at $K_0 = 1.0$). $K_0$ values were taken constant with distance from the wall.

Table 5.1: PLAXIS characteristic soil model input parameters

| Stratum | Top Level | $\gamma_{\rm bulk}$ | $c_{\mathbf{u}}$ | $\phi'$ | c' | $K_0$ | $E_{\mathbf{u}}$ | $E_{\mathbf{d}}$ | ν |
|---|---|---|---|---|---|---|---|---|---|
| Stratum | [mbgl] | [$[kN/m^3]$] | [kPa] | [°] | [kPa] | [ - ] | [kPa] | [kPa] | [ - ] |
| MG | 0.0 | 18.0 | n/a | 30 | 0 | 0.5 | n/a | 5,000 | 0.30 |
| Al undr. | 6.0 | 16.0 | 20.0 | n/a | n/a | 0.58 | 6,000 | n/a | 0.49 |
| Al drained | 6.0 | 16.0 | n/a | 25 | 0 | 0.58 | n/a | 4,500 | 0.30 |
| RTD | 7.0 | 20.0 | n/a | 38 | 0 | 0.38 | n/a | 50,000 | 0.30 |
| LC undr. | 11.0 | 20.0 | 115.0 | n/a | n/a | 1.0 | 92,000 | n/a | 0.49 |
| LC drained | 11.0 | 20.0 | n/a | 25 | 0 | 1.0 | n/a | 69,000 | 0.20 |
| LGC undr. | 17.0 | 20.0 | 160.0 | n/a | n/a | 1.0 | 128,000 | n/a | 0.49 |
| LGC drained | 17.0 | 20.0 | n/a | 27 | 0 | 1.0 | n/a | 96,000 | 0.20 |
| LGS | 27.0 | 20.0 | n/a | 40 | 0 | 1.0 | n/a | 80,000 | 0.20 |
| TS | 33.0 | 21.0 | n/a | 40 | 0 | 1.0 | n/a | 225,000 | 0.30 |
| CH | 47.0 | 19.5 | n/a | 35 | 20 | 1.0 | n/a | 1,500,000 | 0.25 |

where

$\gamma_{\text{bulk}}$ Bulk density

$K_0$ Lateral earth pressure coefficient

$c_u$ Undrained shear strength

$E_{\rm u}$ Undrained Young's modulus

$\phi'$ Eff. stress friction angle

$E_d$ Drained Young's modulus

c' = Cohesion intercept

$\nu$ Poisson's ratio

A concrete mix grade C50/60 with 70% ground granulated blast-furnace slag was used for the reinforced concrete diaphragm walls. The walls were modelled as 1.2 m thick linear elastic plates with an isotropic stiffness of E = 37 GPa. Wall anisotropy due to joints between the panels was not considered. The interface between the soil and the diaphragm wall was simulated with an elastic-plastic model with an interface strength reduction factor $R_{\text{inter}}$ of 0.8 (Brinkgreve et al., 2009).

Figure 5.1 shows the FE mesh adopted in the PLAXIS model. The mesh was made of 735 triangular elements with a refinement in the vicinity of the

diaphragm wall. The figure also shows the boundary conditions, drainage conditions and groundwater levels. Only one half of the problem was modelled due to the symmetry along side AB. The excavation was conducted in 10 m steps between 0 and 60 mbgl; the final step is 13 m between 60 and 73 mbgl. As the FO readings were taken at different excavation levels, the PLAXIS output was linearly interpolated to the excavation levels where FO measurements were obtained.

When the shaft is excavated the diaphragm walls have to withstand the external groundwater and lateral earth pressures in addition to a variable 20 kPa construction surcharge. To obtain the SLS results all loads were multiplied with a partial safety factor of 1.0.

Figure 5.1: Overview of PLAXIS model

Table 5.2: PLAXIS design general input parameters

| 1.2 m               |
|---------------------|
| 84 mbgl             |
| 37.3 GPa            |
| 26.1 GPa            |
| 0.2                 |
| 14.45 m             |
| 0, 10, 20, 30,      |
| 40, 50, 60, 73 mbgl |

## 5.3 Shaft excavation

### 5.3.1 Diaphragm wall curvature and bending moment

As detailed in Section 3.7, the FO measurements of the bending strain cable (BSC) were converted into curvature and bending moment over the depth of the diaphragm wall (Equations 3.9 and 3.10\). The results are presented in two ways: (1) the incremental curvature/ bending moment between two successive excavation levels, *X* and *Y*, ∆*κ*Y−X/∆*BM*Y−<sup>X</sup> and (2) and the absolute curvature/ bending moment where the 0 mbgl dataset has been set as baseline, ∆*κ*Y−0/ ∆*BM*Y−0. The results for the incremental curvature/ bending moment are displayed in Figure 5.2; the absolute curvature/ bending moment in Figure 5.3. A positive value indicates tension on the soil face and compression on the excavation face and hence bending towards the excavation.

Due to the breakages the data for panel P15 in Figure 5.3 is baselined with the 21 mbgl dataset. The loss in pretension between 53 and 75 mbgl at P10 (Section 3.6) resulted in unrealistic values; these data points are therefore omitted from Figures 5.2 and 5.3. For panels P15 and P20 the top 10 m and for panel P10 the top 20 m were lost due to a breakages/ repairs. The datasets taken at shallow excavation levels (< 35 mbgl) are not displayed; the data only shows noise, due to the small bending.

All three panels with FO instrumentation were also equipped with an inclinometer. The inclinometer data could be differentiated, as detailed in Section 4.3.1, to yield curvature (thin lines) which can be compared with FO data (thick lines in Figures 5.2 and 5.3). The inclinometer was interrogated once a week and this was not always at exactly the same day as the FO data acquisition, but in most cases it was only ±1 day apart. It should also be noted that the curvature obtained from the inclinometer does not depend on the error correction assumptions, i.e. the depth position error (DPE) value *d*DPE or the

Figure 5.2: Diaphragm wall incremental curvature/ bending moment between successive excavation levels from FO measurements and inclinometers

Figure 5.3: Diaphragm wall curvature/ bending moment at different excavation levels from FO measurements and inclinometers

fixity depth for the bias correction *z*fix. The figure only shows the results from inclinometer CI1 in panel P10 and BI1 in panel P20; the inclinometer casing of AI1 in panel P15 was blocked with concrete at approximately 60 mbgl and did not provide useful results.

The incremental curvature/ bending moment plots in Figure 5.2 isolate the movement between two excavation levels and cancel out any accumulated errors; hence the bending around excavation level is more obvious. A clear trend can be observed: All measurements show bending towards the excavation below excavation level, and bending away from the excavation above excavation level, forming a bulge. The two independent devices in panel P20 FO (thick red line) and inclinometer (thin red line) are in good agreement, confirming that measurement results are realistic. The inclinometer data from panel P10 also shows a similar magnitude.

In the absolute curvature plots in Figure 5.3 the bending around excavation level is still apparent, but the noise level is higher. Especially for panel P20 there is a high level of noise; this is because the baseline reading was of low quality.

In addition the PLAXIS predictions are plotted on the graph, which were obtained through interpolation from the excavation levels in the PLAXIS analysis to the levels when FO readings were taken. When comparing PLAXIS to the field measurements, it is obvious that the field measurements are larger especially at deeper excavation levels in the Chalk.

### 5.3.2 Diaphragm wall movement

#### 5.3.2.1 Fibre optic instrumentation

The FO instrumentation was configured so that lateral wall movement can be derived. However, the double integrations (Equations 3.11 and 3.12\) over the 84 m deep wall, in combination with the measurement accuracy, accumulated errors, so that the obtained wall movements were unrealistically large. In previous projects, e.g. Schwamb et al. \(2011\) and Mohamad et al. \(2011), the lateral wall movement could be derived successfully; in these cases the walls were significantly shorter, 12 m and 22 m, respectively. Mohamad et al. \(2011\) measured a lateral wall movement of approximately 10 mm, which is also larger than the expected value at Abbey Mills of only 4 mm. For the above stated reasons, the FO instrumentation could not be used to obtain the lateral movement of the diaphragm wall.

#### 5.3.2.2 Shaft inclinometers

The inclinometer data was processed as discussed in Section 4.3.1 to yield the lateral wall movement at different excavation depths. The uncorrected data (not displayed) suggests erratic and large movements, up to more than ±10 mm at capping beam level, which is unrealistic. Additionally, the movement does not occur gradually and for some inclinometers the wall moves away from the excavation. Due to these abnormalities error correction was required; DPE and bias error correction was applied (Section 4.3.3). The corrected lateral wall movement profiles are displayed in Figure 5.4 and the error correction assumptions in Table 5.3.

For deeper excavation levels the bottom of the wall could not be assumed fixed anymore. As detailed in Section 4.3.3.3 and in Figure 4.7, the top of the wall was fixed to the lateral movement of the previous survey. The datasets where this was the case are marked with a *-symbol in Table 5.3. This procedure is very sensitive to the fixity points and hence the data is less reliable.

Inclinometer data from BI1 and CI1 suggests that the wall initially moved as a cantilever during early excavation stages (9, 15 and 21 mbgl) and develops a bulge for deeper excavation levels. AI1 shows no initial cantilever movement, but also bulging at deeper levels - due to the shallower depth of the casing, it is however less reliable.

In addition the PLAXIS predictions are plotted. Reasonably good agreement in magnitude and shape can be observed. PLAXIS however does not show any cantilever movement at shallow excavation levels, while the inclinometers do. Similar findings were reported by Cabarkapa et al. \(2003\) as shown in Figure 2.8.

Above all, the data presents very small wall deflections ∆*u* of less than 4 mm throughout the excavation of a shaft with depth *H* = 71 m, this corresponds to ∆*u*/*H* = 0.0056%. When comparing to non-circular excavations, the ∆*u*/*H* values are significantly larger, in the range of 0.13 to 0.91 % \(Long, 2001). It is expected that circular excavations give smaller movements than cantilever or braced excavations due to a larger system stiffness originating from the hoop effect. This confirms that the Mobilized Strength Design (MSD) method (Equation 2.1, Section 2.3.5\) cannot be applied to circular excavations, as it was based on 110 case studies on braced excavations. This work along with future case studies might provide the necessary field data to derive an MSD approach for circular excavations.

Figure 5.4: Lateral wall movement from shaft inclinometers in comparison with PLAXIS predictions at different excavation levels (positive = towards excavation)

| Exc. Level | dDPE | [mm] |     | zfix | [mbgl] |     |      |
|------------|------|------|-----|------|--------|-----|------|
| [mbgl]     | AI1  | BI1  | CI1 |      | AI1    | BI1 | CI1  |
| 9          | 0    | -50  | -30 |      | 10     | 50  | 30   |
| 15         | 0    | -50  | -25 |      | 27     | 50  | 30   |
| 21         | 0    | -50  | 10  |      | 27     | 50  | 54.5 |
| 35         | 0    | 0    | 30  |      | 47     | 55  | 54.5 |
| 47         | 0    | -20  | 30  |      | 56.5   | 55  | 54.5 |
| 53         | 0    | 0    | 30  |      | 15*    | 57  | 57   |
| 62         | 0    | 0    | 50  |      | 15*    | 65  | 9*   |
| 71         | 0    | 0    | 20  |      | 15*    | 19* | 9*   |

Table 5.3: *d*DPE and *z*fix values for error correction for shaft inclinometers

#### 5.3.2.3 Diaphragm wall optical survey

It was also aimed to use the optical survey of the diaphragm wall targets to deduce wall movements (Section 4.5). However, only the capping beam array provided useful results, as all deeper targets were placed after the excavation level had exposed this level. Hence, any movements before placing the target were not recorded. As discussed in Section 4.5 the eastings ∆*E* and northings ∆*N* are converted into the movement into the shaft ∆*S* and tangential movement ∆*T*. Both are plotted versus time for four out of the eight capping beam targets in Figure 5.5. The actual data is displayed by the round and square markers while the solid lines represent the interpolated and filtered measurements. It can be seen that target T2 moved away from the shaft, while targets T6 and T8 remained at approximately the same position.

To gain a better understanding of how the capping beam deformed, data at the indicated dates is extracted and used to draw deformed shapes in plan view. The results are presented in Figure 5.6. Each sub-figure shows the original shape and the deformed shape. Figure 5.6a provides some further information, such as the target's labels and their corresponding diaphragm wall panels. Targets T4, T6 and T8 were on panels P10, P15 and P20 respectively (for panel layout, please see Figure 3.3b). These panels also included an inclinometer each, CI1, AI1 and BI1 respectively, and may be used to back-up the results. Unfortunately no good correlation was found. This may be due to the assumptions of the inclinometer error correction or the accuracy of the optical survey.

If the data can be trusted it shows that the capping beam did not behave like a rigid non-moving point of fixity. It may not have lengthened or shortened much, but there is potential that it ovalised. Ovalisation may be caused by

<sup>\* =</sup> bias correction according to Figure 4.7

Figure 5.5: Diaphragm wall survey, movement of capping beam targets perpendicular and tangential to shaft wall

Figure 5.6: Original and magnified deformed shape of capping beam from optical diaphragm wall survey at different dates and excavation stages

inhomogeneous ground profiles or excavation process. At Abbey Mills it might be related to the culvert excavation, an approximately 8 m deep conduit for sewage. Its location is shown in Figure 3.2 behind panels P7 and P8 (for panel layout, please see Figure 3.3b\). The excavation of the culvert commenced mid-April and was completed around mid-May 2012 (Figures 5.7a and 5.7c\); two windows were broken through the diaphragm wall (Figure 5.7b\); in August 2012 the base prop for the culvert was cast (Figure 5.7d\). Sump dewatering was applied during the culvert construction and piezometers show that the shallow water level fell by approximately 1.7 m from late April 2012 \(Mott MacDonald, 2012\).

In addition to the plan movement of the shaft, the diaphragm wall survey also provided level movements. These are plotted versus time for all eight capping beam targets in Figure 5.8. It can be seen that the diaphragm wall moved upwards throughout the shaft excavation. When the excavation was completed the head of the wall was approximately 7 to 11 mm higher than before. This may originate from soil swelling caused by the removal of overburden pressure during excavation. Due to this heave and the interface friction between soil and wall, this could also have pushed the wall upwards. This is further investigated in Section 7.3.1.

### 5.3.3 Diaphragm wall hoop strain

#### 5.3.3.1 Measurements

The data from the hoop strain cable (HSC) of the three panels was processed as detailed in Section 3.7. The results are presented in Figure 5.9, separately for each panel and read-out unit (BOTDA or BOTDR). The hoop strain measured at the level of the HSC is plotted versus the excavation depth at the time of measurement. The eight markers represent the different measurement sections in circumferential direction on soil and excavation face as shown in Figure 3.6b. Negative values indicate compression in hoop direction.

It should be noted that the HSC of panels P10 and P20 were attached between 55 and 65 mbgl in the Chalk (shown by the grey box on the figure). Due to the future tunnel opening the HSC of panel P15 is between 41 and 51 mbgl, just above the interface of Thanet Sand and Chalk. Panel P20 (Figures 5.9e and 5.9f\) contains data from only five instead of eight peaks, due to a large bend in the FO cable which caused noisy data at three peaks.

(a) Culvert excavation (16th Apr 2012) (b) Breaking through the wall for the construction of two windows (17th Apr 2012)

(c) Excavation completed, capping beams on the windows were cast (17th May 2012)

(d) Casting of culvert base prop (3rd Aug 2012)

Figure 5.7: Culvert construction (Courtesy of Thames Water)

Figure 5.8: Diaphragm wall survey, level movement of capping beam targets

Figure 5.9: Hoop strain (at HSC level) versus excavation level

The PLAXIS predictions are also plotted in the figures. Hoop strain is obtained by dividing the lateral wall movement predictions by the shaft radius.

Panels P10 and P20 both show a similar trend. It can be observed from Figures 5.9a, 5.9b, 5.9e and 5.9f that the compressional hoop strain in the diaphragm wall (at around 60 mbgl) increases at shallow excavation depths; e.g. at an excavation level of 15 mbgl strains between 0 and -200 µε are measured (this is referred to as 'early-activation'). It then stays relatively constant until the excavation depth reaches the HSC level when a significant increase can be seen as expected; approximately -500 µε ±130 µε is measured at the final excavation depth. The PLAXIS predictions are exceeded significantly at early excavation stages; at deeper excavation levels approximately twice the value is measured.

Panel P15 shows a different trend (Figures 5.9c and 5.9d\). There is no 'early activation' of hoop strain at shallow excavation levels and at the final excavation level the strain is only around -180 µε, which is in good agreement with the PLAXIS predictions.

The 'early-activation' only occurred at deeper levels in the Chalk. Since both panels with the HSC in the Chalk (P10 and P20) confirm this, the measurements appear to be correct. It seems unlikely that the top 15 m of excavation caused hoop strain in the wall at 60 m depth. Due to the nearly impermeable clay layers separating the upper and lower aquifer (Figure 4.1b\) the sump dewatering at the excavation surface cannot have generated a decrease in pore water pressure at depths.

It might be a possibility that creep of the Chalk induced hoop strains in the wall. During the diaphragm wall installation stress states in the Chalk changed and may have led to time-dependant deformation and an increase in radial stress with time. Some studies involving Chalk have reported creep deformation, e.g. Matthews and Clayton \(2004\) and Bell \(1977\). Creep was not considered in the numerical simulations and hence direct comparison of the PLAXIS predictions and the measurements may not be feasible. If the PLAXIS prediction were shifted by -200 µε as shown in Figures 5.9a, 5.9b, 5.9e and 5.9f by the dashed line, they match the data at medium and deep excavation levels better and show a similar trend. Creep rates vary between -140 µε in 64 days (Figure 5.9b\) to -200 µε in 50 days (Figure 5.9f\) for panels P10 and P20 respectively. This corresponds to approximately -2.2 to -4 µε/day.

It is also noted that in panels P10 and P20 the excavation side data points are clearly larger than the soil side data points. This may be related to the verticality of the panels.

#### 5.3.3.2 Earth pressure calculation

The final measurements taken at 71 mbgl, when the excavation depth exceeded the hoop cable depth, can be used to back-calculate the active mobilised earth pressure acting on the shaft *K*a,mob. Assuming that the wall thickness *t* is small in comparison to the diameter *D*, the classical circular arch equation can be used to calculate the incremental hoop stress ∆*σ*θ,

$$\Delta\sigma_{\theta} = -\frac{D}{2t}(\Delta p_{i} - \Delta p_{o}) \tag{5.1}$$

where ∆*p*<sup>i</sup> and ∆*p*<sup>o</sup> are the excavation-induced changes in horizontal pressures acting on the wall from inside and outside, respectively.

According to Hooke's law, the incremental circumferential hoop strain ∆*ε*<sup>θ</sup> is obtained as follows,

$$\Delta \varepsilon_{\theta} = \frac{1}{E} (\Delta \sigma_{\theta} - \nu \Delta \sigma_{r}) \tag{5.2}$$

where ∆*σ*<sup>r</sup> is the change in the radial stress, ∆*σ*<sup>θ</sup> is the change in circumferential stress, *E* is the Young's modulus and *ν* is the Poisson's ratio of the diaphragm wall, assuming an isotropic wall. Under the thin wall approximation, it can be assumed that ∆*σ*<sup>r</sup> ≈ 0.

Assuming wished-in-place (WIP) construction of the diaphragm wall, the incremental internal pressure changes from the total horizontal in situ earth pressure *σ*<sup>h</sup> to 0, and hence

$$\Delta p_{\rm i} = 0 - (K_0(\sigma_{\rm v} - u_0) + u_0) \tag{5.3}$$

where *K*<sup>0</sup> is the horizontal earth pressure coefficient at rest, *σ*<sup>v</sup> is the total vertical in situ earth pressure, and *u*<sup>0</sup> is the pore water pressure.

The incremental external pressure ∆*p*<sup>o</sup> ̸= 0, as the wall movement causes a pressure change from *K*<sup>0</sup> to a mobilised active earth pressure *K*a,mob.

$$\Delta p_{\rm o} = (K_{\rm a,mob}(\sigma_{\rm v} - u_0) + u_0) - (K_0(\sigma_{\rm v} - u_0) + u_0) \tag{5.4}$$

The *K*0-terms cancel out and an expression for the mobilised active earth pressure can be obtained,

$$K_{\text{a,mob}} = \frac{2E\Delta\varepsilon_{\theta}t/D - u_0}{\sigma_{\text{v}} - u_0} \tag{5.5}$$

### Monitoring results

For the earth pressure coefficient back-calculation the measurements of panels P10 and P20, which both show a similar trend, were used. Average hoop strains of approximately -500 µε were measured at an excavation level of 71 mbgl. With *t* = 1.2 m, *E* = 37 GPa, *D* = 28.9 m, *u*<sup>0</sup> = 365 kPa and *σ*<sup>v</sup> = 1180 kPa this yields an active earth pressure coefficient *K*a,mob in the Chalk of 1.4. This value is larger than the initial *K*<sup>0</sup> as the measurements include the creep which may have occurred at early excavation stages. It should also be noted that this equation is highly sensitive to the wall thickness *t* and concrete Young's modulus *E*. In reality the effective wall thickness of the ring structure is likely to be less than 1.2 m, owing to the non-verticality of the panels. Site records show a verticality value (expressed as the ratio of the horizontal offset at the bottom of the wall to the vertical depth of the wall) of 1:400. Assuming 1:400 in one direction and 1:800 in the other direction this is equivalent to a 0.23 m reduction in wall thickness at a depth of 60 mbgl where the hoop strains were measured. With an effective wall thickness of *t* ′ = 0.97 m, Equation 5.5 yields a *K*a,mob of 1.1. If in addition the wall stiffness is decreased or increased by 20 % the *K*a,mob values range from 0.8 to 1.4, respectively.

The measurement accuracy and the variability of the input parameters do not allow reliable back-calculation of earth pressure acting on the shaft, they do however show that the measured values are realistic. Earth pressures will be further investigated numerically in Section 7.2.6.

### 5.3.4 Ground movement

#### 5.3.4.1 Vertical ground movement

As shown in Figure 3.2 and as detailed in Section 4.4, there were eight surface levelling pins around the shaft. The results of the optical survey are presented in Figure 5.10 where the vertical movement of the targets is plotted versus time. The excavation progress is displayed on the secondary y-axis, which shows that the survey only started at an excavation level of approximately 20 mbgl.

During shaft excavation most targets remained within ±2 mm vertical movement, whereas it would be expected that the ground surface heaves similarly to the capping beam targets as shown in Figure 5.8. This may be related to the different baselines; the diaphragm wall survey started with shaft excavation, while the surface levelling survey only started at an excavation level of 20 mbgl.

The measurements do also not follow a particular pattern and seem to be

within accuracy. When the shaft excavation was completed all targets (apart from 6100 and 6101, Figure 5.10b) settled gradually to values between -1 and -3 mm. Targets 6100 and 6101 remained approximately at 0 mm settlement.

After consultation with site engineers it was concluded that the levelling pins, road nails drilled and glued into the concrete platform, were influenced by the heavy site traffic and the crane locations. The data does hence not properly represent the excavation-induced vertical surface movement and only shows that the concrete platform has undergone settlements smaller than 3 mm.

Apart from the levelling pins, there were rod and magnet extensometers around the shaft to measure vertical subsurface ground movement (Section 4.2). The rod extensometer data, recorded from September 2011 until June 2013 (Figure 3.3a), was baselined on the 2nd of April 2012 when excavation started to isolate the excavation-induced movement. The results of the four rod extensometer boreholes are shown in Figure 5.11. Each rod extensometer had six anchors over its depth; the deepest anchor is used as stable reference and is thus not displayed (Equation 4.1). On the secondary y-axis the excavation progress is plotted, as well as the ground profile with the anchor depths (indicated by the coloured circles, same colour as graph).

Figure 5.10: Surface settlement from optical survey of levelling pins

### Monitoring results

Some graphs are discontinuous and have gaps; at these times the data logger recorded very noisy data which was omitted. For BE1 (Figure 5.11c\) the bottom sensor stopped recording in February 2012. All subsequent data is hence not baselined anymore.

Above all, the data presented in Figure 5.11 shows that extremely small vertical movement occurred throughout shaft excavation; the maximum relative settlement is 1.4 mm.

Both rod extensometers in 2.5 m distance from the shaft wall AE1 and BE1 in Figures 5.11a and 5.11c show hardly any movement, the values remain within +0.25 and -0.5 mm. The rod extensometers at 6 m distance AE2 and BE2 in Figures 5.11b and 5.11d recorded slightly more settlement between 0 and 1.4 mm for the various anchors over depth. It can also be observed that anchors at shallow depths settle more than those at deep depth, as expected

As detailed in Section 4.2, the rod extensometer data was baselined with the bottom anchor. The presented results are hence only valid if the bottom anchor has not moved. Movement of the bottom anchor could have been induced by soil swelling due to the removal of overburden pressure inside the shaft at excavation level. Movement could have also been generated by a change in ground water level, such as caused by water flow around the toe of the wall inside the excavation where sump dewatering was applied. Other dewatering activities in the area, not related to Abbey Mills shaft, also resulted in small changes of water level. Mott MacDonald \(2012\) reports that the deep aquifer level fell by approximately 0.5 m/month between December 2011 and August 2012. Initially it was planned to use a borehole head survey to baseline the rod extensometer measurements. This was however not possible due to the low accuracy of this survey.

In further distance from the shaft magnet extensometers were installed (Section 4.2.2\). The results from one borehole, AE3, is displayed in Figure 5.12 showing the vertical movement of the six spider magnets at different depths versus time. The data seems noisy between +10 and -20 mm, showing no particular trend. Especially when considering the small movements measured closer to the shaft with the rod extensometers, it appears that magnet extensometers do not offer good enough resolution for the purpose of measuring movements in the order of millimetres; this can already be observed from the interrogation method (Figure 4.2e\).

Figure 5.11: Subsurface settlement from rod extensometers: vertical movement of each anchor versus time, excavation level versus time and ground profile with anchor locations

Figure 5.11: *(Cont.)* Subsurface settlement from rod extensometers: vertical movement of each anchor versus time, excavation level versus time and ground profile with anchor locations

Figure 5.12: Subsurface settlement from magnet extensometer AE3: vertical movement of each spider magnet versus time

#### 5.3.4.2 Horizontal ground movement

Apart from the shaft inclinometers there were six further inclinometers around the shaft (AI2, AI3, AI4, BI2, BI3 and BI4), as shown in Figure 3.2. The bias and DPE corrected results for all six inclinometers at different excavation levels are displayed in Figure 5.13. The error correction assumptions can be found in Table 5.4. For the deeper excavation levels bias correction was not possible, as no *z*fix could be determined anymore ('x' in the table), as no part of the inclinometer casing could be assumed stable.

It can be seen that the overall horizontal movement is very small, less than +2 mm, not considering the less reliable surveys without bias correction in Figures 5.13f and 5.13g.

| Exc. Level |     | dDPE<br>[mm] |     |     |     |     | zfix<br>[mbgl] |      |     |      |      |     |
|------------|-----|--------------|-----|-----|-----|-----|----------------|------|-----|------|------|-----|
| [mbgl]     | AI2 | AI3          | AI4 | BI2 | BI3 | BI4 | AI2            | AI3  | AI4 | BI2  | BI3  | BI4 |
| 9          | -10 | -50          | 0   | -15 | -50 | 0   | 13.5           | 32.5 | 0.5 | 20   | 21.5 | 12  |
| 15         | 0   | -40          | 0   | 0   | -15 | 0   | 13.5           | 32.5 | 0.5 | 20   | 21.5 | 12  |
| 21         | 0   | -5           | 0   | 20  | 5   | 0   | 47.5           | 32.5 | 0.5 | 20   | 21.5 | 12  |
| 35         | 20  | 0            | 0   | 40  | -10 | 0   | 47.5           | 32.5 | 0.5 | 48.5 | 41.5 | 12  |
| 47         | 30  | -10          | 0   | 30  | -10 | 0   | 47.5           | 32.5 | 0.5 | 48.5 | 41.5 | 12  |
| 53         | 20  | -60          | 0   | 30  | -10 | 0   | x              | 40   | 0.5 | x    | 41.5 | 12  |
| 62         | 35  | 20           | 0   | 25  | -20 | 0   | x              | x    | 0.5 | x    | x    | 12  |
| 71         | 35  | 0            | 0   | 30  | 0   | 0   | x              | x    | 0.5 | x    | x    | 12  |

Table 5.4: *d*DPE and *z*fix values for error correction for soil inclinometers

x = no bias correction applied

Figure 5.13: Lateral ground movement from soil inclinometers at different excavation levels (positive = towards excavation)

## 5.4 Diaphragm wall construction

During the diaphragm wall construction only the soil instrumentation was in place. For the inclinometer data analysis it was not possible to fix the bottom of the borehole to zero movement, as the panel excavation depth of 84 m was deeper than the inclinometer boreholes (Figure 4.1b\). When plotting the shapes of the lateral displacement profiles (not displayed), it was obvious that the noisy data would require error correction. For the bias correction a 2nd point of fixity *z*fix would be necessary, which was not possible due to the same reason as stated above. Horizontal ground movement during diaphragm wall installation might be significantly larger than during shaft excavation. For future instrumentation schemes it is recommended to extend the boreholes deeper than the walls to capture installation effects.

The rod extensometer results for all four boreholes are displayed in Figure 5.14. Apart from the relative settlement profiles of the five anchors (baselined with the bottom anchor, according to Equation 4.1\), further information is given in the figure: The grey and blue rectangles show when the diaphragm wall panels were excavated and concreted; the location of the panels relative to the boreholes can be found on the bottom left schematic. On the right of each figure the ground profile with the anchor depths can be found.

At the end of the diaphragm wall construction, on the 9th of December 2011, the highest anchors at 7.3 and 8.1 mbgl of boreholes AE1 and AE2 (Figures 5.14a and 5.14b\) recorded a settlement of 2 mm. In the boreholes BE1 and BE2 (Figures 5.14c and 5.14d\) larger settlements were measured: The anchors at 11.2 and 17.3 mbgl of BE1 show 6 mm settlement, while the surface only settles approximately 4.5 mm; the highest anchor at 8.3 mbgl in BE2 records 4 mm settlement at the end of the diaphragm wall construction. The results are again subject to a stable bottom anchor, as detailed in Sections 4.2.1 and 5.3.4.1.

In comparison to the excavation-induced movement (between +0.2 and -1.4 mm) these values are significantly higher, showing that the wall installation causes larger soil movement than the shaft excavation. Similar findings were reported by Muramatsu and Abe \(1996\) as shown in Figure 2.16b.

It was also aimed to correlate the trench excavation and concreting of the panels next to the boreholes to the settlement profile (panel excavation and concreting times are shown with the coloured rectangles). However, no specific pattern was found.

Figure 5.14: Rod extensometer measurements during diaphragm wall construction including panel excavation and concreting dates, as well as ground profile with anchor depth (right)

Figure 5.14: (*Cont.*) Rod extensometer measurements during diaphragm wall construction including panel excavation and concreting, as well as ground profile with anchor depth (right)

## 5.5 Dewatering trial

During the dewatering trial the water level from the deep aquifer (Figure 3.1\) inside the shaft was lowered from approximately 24 to 70 mbgl. Two wells W1 and W3 were used to pump the water, while well W2 was used to measure the drawdown in a distance, as shown in Figure 3.3c. The rod extensometer data (not displayed) seems unaffected; no settlement around the shaft is recorded, which is in line with the unchanged water levels \(Mott MacDonald, 2012\).

Inclinometer readings were not taken during the dewatering trial. The FO BSC did not produce useful results; the strain induced by the dewatering trial might have been too low to exceed the noise level.

The results from the HSC are displayed in Figure 5.15. Figure 5.15a plots the hoop strain changes for each panel between the two baseline datasets BD1 and BD2 (Table 3.2\). Figure 5.15b plots the hoop strain changes between the dataset taken during the dewatering trial DD and the 2nd baseline dataset BD2. The eight markers represent the different measurement sections in circumferential direction on soil and excavation face as shown in Figure 3.6b.

No change in hoop strain would be expected between the two baseline datasets. However, as shown in Figure 5.15a average compressional strains of approximately 100 µε were measured in panels P10 and P20, while panel P15 remained unchanged on average as would be expected. As only the panels in the Chalk show this effect, this may also be related to creep of the Chalk as discussed in Section 5.3.3.1. The rate of creep is approximately ≈ -6 µε/day which is larger than during early excavation stages. This indicates that the creep rate was reducing.

From Figure 5.15b it can be observed that during the dewatering stage panels P15 and P20 experienced compression between 100 and 400 µε while panel P10 exhibits tensile strains of approximately 100 µε.

These measurements indicate that a three-dimensional deformation mechanism may have resulted as a consequence of different pumping operations of the three dewatering wells and the distance of the panels from the wells. Figure 5.15b shows that the water levels in wells W1 and W3 were both pumped to 70 mbgl during the trial. No dewatering was conducted from well W2; this well was used to measure the water table drawdown in a distance from the other pumped wells. These measurements show that the water levels inside the shaft did not fall uniformly; the water level in well W2, located 18 m away from

(a) Before dewatering trial: Differential hoop strain between datasets BD1 and BD2 (9th and 26th January 2012, Table 3.2\)

(b) During dewatering trial: Differential hoop strain between datasets BD2 and DD (26th January and 2nd February 2012, Table 3.2\)

Figure 5.15: Hoop strain measurements before and during dewatering trial

### Monitoring results

wells W1 and W3 remained at 66 mbgl, i.e. 4 m higher than the pumping level. When considering the well locations in comparison to the panels (Figure 3.2\) it is reasonable to assume that the water level on the wall at panel P10 was likely to be higher than the water level at panels P15 and P20. This may have caused the wall to deform non-uniformly; the sections with lower water pressures compressing and the sections with higher water pressure getting pushed away from the centre and may hence exhibit tensile strains. It should also be noted that the measurements for panel P10 were taken only around 2.5 hours after pumping had started. Even though the water levels in the wells were lowered, the surrounding water pressure may have not been allowed sufficient time and hence may have not reached steady state conditions.

The measurements of panels P10 and P20 show lower hoop strains on the soil side, which is consistent with the observations in Section 5.3.3.1, and probably related to the verticality of the panels.

## 5.6 Annulus infill

The results obtained from the monitoring during annulus infill on the 8th and 9 th of April 2013 (Table 3.2\) are displayed in Figure 5.16.

The FO BSC cable provides the differential curvature between the dataset before the annulus infill BA and the one after AA (Figure 5.16a\). Panels P15 and P20 show similar trends; around the base slab negative curvatures of around −0.7 × 10−<sup>4</sup> m−<sup>1</sup> are recorded and above the base slab positive values up to 1.4 × 10−<sup>4</sup> m−<sup>1</sup> . With a Young's modulus of *E* = 37 GPa and wall thickness of *t* = 1.2 m the curvature can be converted to bending moment; these values correspond to approximately -370 kNm and 750 kNm and are of a similar magnitude as the excavation-induced bending moments (Figure 5.3\). To investigate if the shape of the obtained results seems reasonable, a simplified system as shown in Figure 5.16a is considered. A triangular pressure difference between annulus infill and soil is assumed and applied to the wall, which is supported by a roller at the capping beam and a full fixity below the base slab. The obtained bending moment shape (thick grey line in Figure 5.16a\) matches reasonably well with the measurements.

From the shaft inclinometers the lateral wall movement can be obtained. The uncorrected data is presented in Figure 5.16b. DPE correction was not necessary and for the bias correction it was not possible to find a fixity point.

Figure 5.16: Monitoring results from annulus infill

### Monitoring results

The inclinometers AI1 and BI1 show a similar deformation. Above slab level the diaphragm wall is pushed away due to the infill pressure. The maximum movement is less than 3 mm away from the shaft into the soil.

The differential vertical ground movements from the rod extensometers is displayed in Figure 5.16c. Most anchors show small heave; at the surface the largest values are measured (1.2 mm for BE1).

## 5.7 Discussion of the fibre optic monitoring scheme

Abbey Mills site was one of the first project where FO instrumentation was installed in very deep walls and where hoop strain was measured. Several advantages and limitations of the FO monitoring scheme are discussed below.

The FO installation was challenging, as the reinforcement consisted of several pieces and the FO cables had to be bridged over the splices. Nevertheless, the FO installation did not delay the construction process owing to the Fujikura pretension clamp and the good cooperation with the contractor JV MVB.

After installation the FO cables were routed to a monitoring hut through a ducting in the concrete platform specifically designed for the FO cables and the conventional rod extensometers. The hut provided protection and shelter which are essential while carrying out delicate splicing work and handling sensitive instruments. The cables remain in the hut and further measurements can be taken in the future if required. The inclinometer boreholes, on the other hand, might be obstructed and not accessible anymore.

FO cables are versatile and can be arranged in any required configuration, e.g. to measure the hoop strain. In comparison to conventional instrumentation (e.g. vibrating wire strain gauges) only one FO cable is required to measure hoop strain at several depths instead of one cable per strain gauge.

The FO BSC provided direct measurements of curvature and bending moment. It was however not possible to perform the double integration to obtain the wall deflection. The deep walls and the small movement in combination with the measurement accuracy caused error accumulation during the integrations. The inclinometer on the other hand gave reasonable wall deflection profiles. It should however be noted that heavy error correction was required.

In this project FO data was taken manually, but it is also possible to take automatic measurements, if the read-out unit can stay on site throughout the duration of the project. Inclinometer measurements can also be performed

automatically, but the costs increase significantly and the resolution decreases (manual inclinometers take inclination measurements every 0.5 m depth, while the in-place-inclinometer only allows intervals of 2 to 5 m).

The FO instrumentation is fragile and breakages of the cable can occur if not enough care is taken (several improvements were suggested in Section 3.6\). For future installations it is advised to use a more robust cable.

When analysing the FO raw data to the required output, it proved important to adjust any alignment misfit of the raw data as detailed in Section 3.7.2.1. The data analysis was carried out in MATLAB which provides more flexibility in comparison to Microsoft Excel which was previously used. MATLAB allows to interpolate the data from a 10 cm resolution (as provided by the read-out unit) to any required smaller interval (in this case 1 cm was sufficient). An auto-correlation algorithm was developed to adjust the datasets for any misalignment. This significantly improved the quality of the results.

From the author's point of view the following aspects have to be addressed in order for FO instrumentation to become more applicable and more widely-used:

**Costs:** While standard telecommunication FO cables are relatively cheap (less than £1/m), strain sensing cables are expensive (Fujikura strain sensing fibre costs approximately £15/m). With increasing demand for strain sensing cables, it would be possible to produce these in a similar price range to telecommunication cables.

**Robustness:** More robust strain sensing FO cables have become available on the market in recent years. For future projects it would be recommended to use more robust fibres as for example introduced by Iten \(2011\).

**Automated monitoring:** The monitoring industry tends to prefer automatic monitoring systems. Hence FO monitoring has to move to automatic readings where the read-out unit can stay on site. This may require the use of a multiplexer which allows to take readings of several input FO cables.

**Data analyses:** Along with automated monitoring a software package is required to carry out the data analysis as soon as the readings are taken and inform the user immediately of potential problems. This may be difficult, as up to now each project required a customised and adaptable analysis. With a more standardised and robust installation it may be possible to develop a generic data analyses software.

## 5.8 Summary of key findings

- **Wall bending:** The excavation-induced curvatures/ bending moments exceeded the PLAXIS predictions; especially at deeper excavation levels in the Chalk. Inclinometer and FO measurements both confirm this. The measurements during annulus infill are of a similar magnitude as the excavation-induced values.
- **Wall movement:** The shaft inclinometer data shows small cantilever movement at shallow excavation stages and a bulge forming at deeper levels. The overall wall deflections were smaller than 4 mm, which is similar to the numerical predictions. The annulus infill caused movements of less than 3 mm in the opposite direction.
- **Ground Movement:** Measurements indicate very small ground movements during shaft excavation. The rod extensometer recorded maximum settlements of 1.5 mm and the soil inclinometers suggest less than 2 mm horizontal movement towards the shaft. The majority of vertical soil movement occurred during diaphragm wall construction; settlements up to 6.5 mm were recorded. During the annulus infill small heaves between 0 and 1.2 mm were measured. The rod extensometer data is subject to the assumption of a stable bottom anchor.
- **Ovalisation:** The optical diaphragm wall survey suggests that the shaft may have ovalised during early excavation stages, probably due to the culvert excavation behind the eastern shaft wall.
- **Hoop strain:** The measured hoop strains in the Chalk exceed the predictions at early excavation stages and before excavation when no strains were expected. This may be related to creep of the Chalk. The measurements were furthermore used to back-calculate earth pressure acting on the shaft wall, which indicate a mobilised active earth pressure *K*a,mob in the range of 0.8 to 1.4. This value is highly sensitive to the input hoop strain, the wall thickness and the concrete Young's modulus. The hoop strains measured during the dewatering trial indicate that the shaft may have experienced small three-dimensional deformation due to different water pressures.
- **Resolution of instrumentation:** The magnet extensometers are not accurate enough to measure the small ground movements. The optical surface survey seems to be influenced by site traffic.

# Chapter 6

## Numerical simulation

## 6.1 Introduction

To gain a better understanding of the shaft's performance, the monitoring results (Section 5.3\) are compared to a parametric study conducted with the finite difference package FLAC. This chapter provides the details and input parameters for the simulations.

## 6.2 Overview

FLAC stands for 'Fast Lagrangian Analysis of Continua' and is a two-dimensional explicit finite difference program.

The shaft was modelled using axisymmetric mode where the *z*-axis is the axis of symmetry. The model as displayed in Figure 6.1 is approximately 93 m wide and 120 m deep and contains 12960 elements (Table 6.1\). All soil elements are 1 m x 1 m; only the first column of elements is only 0.85 m wide. As FLAC does not allow the use of structural elements in axisymmetric mode, the wall was modelled using solid elements with six 0.2 m wide elements across the width of the wall (Figure 6.1 close-up view). An interface was placed between soil and wall extending 1 m below the toe of the wall. The applied mechanical and fluid boundary conditions are displayed in the figure, as well as the assigned pore water pressure distribution. Further details can be found in Figure 6.1 and Table 6.1.

FLAC was used to run a model similar to the PLAXIS design, which is referred to as 'FLAC1'. Further analyses incorporating advanced features and the parametric study were run with the model 'FLAC2'.

Figure 6.1: Overview of FLAC model

Table 6.1: FLAC model details

| Height                   | 120 m                           |
|--------------------------|---------------------------------|
| Width                    | 93 m                            |
| Number of elements       | 12960                           |
| Gravity                  | $10\mathrm{m/s^2}$              |
| Water density            | $1000  \text{kg/m}^3$           |
| Fluid bulk modulus $K_f$ | $2.2 \times 10^{-9} \text{ Pa}$ |

## 6.3 Modelling procedure

Ideally a fully coupled modelling approach would be used. However due to the large permeability contrast the associated time step was very small and it would be very time-consuming to run the full excavation problem. Hence, an uncoupled approach where the fluid flow calculations are uncoupled from the mechanical calculations was applied. This does however not allow real time to be involved in the calculations.

The two model approaches suggested in Itasca \(2011b, Section 1.8.2.1) were combined for the FLAC runs carried out in this study: The London Clay and the Lambeth Group Clay were modelled as fully undrained and all other layers as drained. Effective stress based soil models were used and the undrained condition was modelled by adding the stiffness of the pore fluid to the overall material stiffness. Only mechanical calculations were performed, as the fluid flow is negligible and can be switched off. For the drained material the analysis is conducted in two steps: (1) the fluid step where the steady-state pore pressure field is determined and (2) the mechanical step where the model is cycled to equilibrium under the constant pore pressure field.

To model the full excavation problem, the following steps were carried out:

**Initial equilibrium:** In the first step the mesh is generated, as displayed in Figure 6.1. The mechanical and fluid boundary conditions, soil properties and initial stresses are assigned. Gravity, water density and fluid bulk modulus are also specified (Table 6.1\). The model is then cycled to equilibrium.

**Wall installation:** For the FLAC1 model the wall is assumed to be wished-inplace (WIP). In this case, the procedure detailed below is skipped. For some FLAC2 models the wall installation is modelled. A similar approach as suggested by Lings et al. \(1994\), Gourvenec and Powrie \(1999\) and Conti et al. \(2012\) is applied here. The solid elements of the future wall are removed and the bentonite pressure is applied as total stress, as shown in Figure 6.2 by the orange arrows. After this has reached equilibrium additional pressure which represents the wet concrete is applied, as shown in Figure 6.2 by the purple arrows.

**Wall solid elements & interface:** In this step the solid elements of the wall are assigned their material model, properties and initial stresses and the interface between soil and wall is activated. The interface behaviour is described with an elastic-plastic Mohr-Coulomb criterion. Its properties are based on the PLAXIS model, which used an interface strength reduction factor *R*inter of 0.8. The interface cohesion value *c*inter is obtained by *R*inter · *c* ′ \(Brinkgreve et al., 2009\) where *c* ′ is the ground cohesion; this yields 16 kPa for the interface between the wall and the Chalk and 0 for all other layers. An average friction angle of *φ* ′ = 35° was used to determine the interface friction angle *φ*inter = arctan(*R*inter · tan*φ* ′ ) \(Brinkgreve et al., 2009\) to approximately 30° which was assigned to all layers.

**Excavation:** The excavation process is carried out in 1 m steps.

For the excavation above the London Clay the pore pressure at excavation level and 1 m below is set to 0 and fixed, i.e. drainage is allowed (Figure 6.3\). FLAC automatically adjusts the total stresses; a flow step is not required as the clay layers act as a impermeable barrier. The top row of elements is then removed and the model is cycled to equilibrium with the mechanical calculations set on and the flow calculations set off.

When excavation reaches the clay layers dewatering is not required anymore. The top row of elements is removed and the fluid boundary condition at the excavation level is set not to allow drainage. The cycling to equilibrium is again conducted with mechanical calculation on and flow calculations off.

For the excavation below the clay two sub-steps are required: (1) the flow step and (2) the mechanical step. For the former the pore pressure is set to 0 at excavation level and 1 m below, similar to Figure 6.3. The model is then stepped to steady-state with mechanical calculations off and flow calculations on. For (2) the top row of elements is removed, the mechanical calculations are turned on, the flow calculations are set off and the model is cycled to equilibrium.

Figure 6.2: Modelling diaphragm wall installation

Figure 6.3: Modelling of excavation

## 6.4 Constitutive soil models

### 6.4.1 Overview

The Abbey Mills shaft penetrates several ground layers (Figure 4.1b). The thinner layers, i.e. the Alluvium, the Harwich Formation and the Calcrete are not explicitly modelled. For the simplified FLAC1 model the remaining seven groups, i.e. Made Ground, River Terrace Deposits, London Clay, Lambeth Group Clay, Lambeth Group Sand, Thanet Sand and Chalk, were assigned the Mohr-Coulomb (MC) model. The input parameters can be found in Table 6.4.

In FLAC2 the Made Ground, River Terrace Deposits, London Clay, Lambeth Group Clay are also modelled with the MC model. For the clays a hyperbolic stiffness degradation function was implemented. Lambeth Group Sand and Thanet Sand are modelled with a Strain-Hardening/ Softening (SHS) model; the Hoek-Brown (HB) model was used for the Chalk. This is further detailed below and an overview as well as the input parameters for the soil layers are provided in Table 6.5.

### 6.4.2 Mohr-Coulomb model

The MC model simulates elastic soil behaviour before yield. The failure envelope that defines the onset of yield comprises two functions: (1) the shear yield function  $f^s$  (Equation 6.1) and (2) the tension yield function (Equation 6.2),

$$f^{\rm s} = \sigma_1' - \sigma_3' N_\phi + 2c' \sqrt{N_\phi} \tag{6.1}$$

$$f^{t} = \sigma^{t} - \sigma_{3}' \tag{6.2}$$

where  $\sigma'_1$  and  $\sigma'_3$  are the principal effective stresses (compressive stresses are negative),  $\sigma^t$  is the tension cut-off, c' is the cohesion intercept,  $\phi'$  is the effective stress friction angle and

$$N_{\Phi} = \frac{1 + \sin \phi'}{1 - \sin \phi'} \tag{6.3}$$

Yield occurs when either  $f^s$  or  $f^t$  are equal to 0.

The behaviour after yield is governed by a non-associated flow rule (for shear flow) and an associated flow rule (for tension flow). Further details can be found in Itasca (2008).

All FLAC1 layers are modelled with the MC model and input parameters are tabulated in Table 6.4. In FLAC2 the MC model is assigned to the Made Ground and River Terrace deposits and the input parameters are the same as in FLAC1 (Table 6.5\).

### 6.4.3 Stiffness degradation function

FLAC's integrated MC model detailed above was assigned to the London Clay and Lambeth Group Clay and small-strain stiffness degradation before yield was incorporated with a so-called 'FISH-function'. FISH is a programming language in FLAC allowing the user to write functions, new constitutive models, etc.

The FISH-function calculates the shear stress *τ* according to Equation 6.4 \(Pyke, 1979\),

$$\tau = \tau_{\text{ref}} + \frac{G_{\text{max}} \cdot (\gamma - \gamma_{\text{ref}})}{1 + \frac{a}{n} \cdot |\gamma - \gamma_{\text{ref}}|} \tag{6.4}$$

where *G*max is the shear modulus at very small strain, *a* is a constant, *n* depends on loading/ unloading conditions, *γ* is the current shear strain, *τ*ref and *γ*ref are the reference shear stress and strain which are set to the values of the last strain reversal as shown in Figure 6.4a. The equation can be simplified for first time loading (*γ*ref = *τ*ref = 0) to

$$\tau = \frac{G_{\text{max}} \cdot \gamma}{1 + \frac{a}{n} \cdot \gamma} \tag{6.5}$$

The stress-strain relationship used here is displayed in Figure 6.4a; a perfect loop closure was adopted, as no cyclic loading is expected. The value of *n* is either 1 (for first time loading) or 2 (for unloading and reloading). After the maximum strain is exceeded, *n* is set to 1 again as shown in Figure 6.4a.

The secant shear modulus *G*<sup>s</sup> is then calculated as follows,

$$G_{\rm s} = \frac{\tau - \tau_{\rm ref}}{\gamma - \gamma_{\rm ref}} \tag{6.6}$$

To avoid numerical instabilities *G*<sup>s</sup> ≥ *G*max/10.

*G*max and *a* were determined by matching *G*<sup>s</sup> with triaxial test data. For the London Clay the undrained triaxial test 25gUC carried out by Gasparre \(2005\) was picked; details on the test are given in Table 6.2. This test was picked, as it was conducted with a mean effective stress in a similar range of what is expected in the London Clay at Abbey Mills. Gasparre \(2005\) plots shear modulus versus shear strain ε_s; ε_s had to be converted to match FLAC's definition of shear strain *γ* as follows

$$\gamma = \frac{\sqrt{3}}{2} \cdot \varepsilon_{\rm s} \tag{6.7}$$

Figure 6.4b shows Gasparre's \(2005\) measured shear modulus *G*<sup>s</sup> versus *γ*. The hyperbolic function with *G*max = 80 MPa and *a* = 4500 matched the triaxial data best.

Data for the Lambeth Group Clay was taken from CIRIA C583 \(Hight et al., 2004\) which provides values of undrained Young's modulus normalised by the mean effective stress. This was converted into the shear modulus with a mean effective stress of 450 kPa (mid-depth of the 10 m thick layer). The results are plotted in Figure 6.4c. The best fit was achieved with *G*max = 500 MPa and *a* = 18000.

The complete input parameters for the London Clay and Lambeth Group Clay are listed in Table 6.5.

Table 6.2: Details of triaxial test used to determine stiffness degradation curve for London Clay \(Gasparre, 2005\)

| Test Name                     | 25gUD                                |
|-------------------------------|--------------------------------------|
| Location                      | Heathrow T5                          |
| Lithological unit             | B2                                   |
| Test Type                     | Undrained Compression                |
| Initial eff. stress           | 350 kPa                              |
| Stress state before shearing  | p' = 420 kPa, q = -154 kPa |
| Sample diameter               | 100 mm                               |
| Depth from ground level       | 25 m                                 |
| Depth from top of London Clay | 19 m                                 |


#### (a) Stress-strain relation

(b) Triaxial data by Gasparre \(2005\) and hyperbolic match

(c) Data from CIRIA C583 \(Hight et al., 2004\) and hyperbolic match

Figure 6.4: Stiffness degradation for London Clay and Lambeth Group Clay

### 6.4.4 Strain hardening/ softening model

The SHS model is based on the MC model (Section 6.4.2\) with elastic material behaviour before yield. After the onset of yield the cohesion, friction, dilation and tensile strength can harden or soften. Piecewise linear functions of these parameters versus axial plastic strain *ε*ap can be input into FLAC \(Itasca, 2008\).

The elastic parameter for Lambeth Group Sand and Thanet Sands were taken from the design report (i.e. same as in Table 5.1\). The plastic behaviour is modelled according to one of Ventouras' \(2005\) triaxial tests. The test RS17 (details see Table 6.3\) is used to curve-fit the piecewise linear functions. This test was picked as the sample's confining pressure was close to what would be expected and the location of the site was close to Abbey Mills. The stress ratio *q*/*p* ′ and the volumetric strain *ε*<sup>v</sup> versus the axial strain *ε*<sup>a</sup> were extracted from Ventouras' \(2005\) triaxial test (Figures 6.5a and 6.5c\). The onset of yield was picked at an axial strain *ε*<sup>a</sup> = 5 % and a volumetric strain *ε*<sup>v</sup> = 2 %. This yields a Poisson's ratio *ν* of 0.3, similar to the design parameters in Table 5.1, which shows that the selected onset of yield was appropriate.

To obtain the input functions for FLAC, the effective stress friction angle *φ* ′ and the dilation angle *ψ* were extracted according to the following equations and then plotted versus axial plastic strain, *ε*ap = *ε*<sup>a</sup> −5% (Figures 6.5b and 6.5d\).

$$\sin \phi' = \frac{3q/p'}{6 + q/p'} \tag{6.8}$$

$$\psi = \arcsin \frac{\delta \varepsilon_{\rm v} / \delta \varepsilon_{\rm a}}{\delta \varepsilon_{\rm v} / \delta \varepsilon_{\rm a} - 2} \tag{6.9}$$

Equation 6.9 was derived from Vermeer and de Borst's \(1984\) bilinear idealisation of triaxial test results.

The piecewise linear functions were fitted to the data as shown in Figures 6.5b and 6.5d. These were used for the Thanet Sand and the Lambeth Group Sand; the other input parameters apart from these are given in Table 6.5.

Table 6.3: Details of triaxial test used for SHS model for Thanet Sand and Lambeth Group Sand \(Ventouras, 2005\)

| Test Name               | River Side #22 (RS17) |
|-------------------------|-----------------------|
| Test Date               | 20/06/2004            |
| Silt Content            | Low                   |
| Initial specific volume | 1.761                 |
| Sample state            | Reconstituted         |
| Test Type               | Drained Compression   |
| Confining pressure      | 0.55 MPa              |
| Sample diameter         | 38 mm                 |

Figure 6.5: SHS model: fitting piecewise linear functions to the effective stress friction angle and dilation angle from test RS17 taken from Ventouras \(2005\)

### 6.4.5 Hoek-Brown model for Chalk

The HB model is a failure criterion for rock material; it is not a full constitutive model. In addition to the failure criterion, which is in FLAC taken as a yield surface, the model requires a stress-strain relation before yield and a flow rule after yield.

Yield onsets when the yield function  $f^{hb} = 0$ ,

$$f^{\text{hb}} = \sigma_3' - \sigma_1' + \sigma_{\text{ci}} \left( m_b \frac{\sigma_3'}{\sigma_{\text{ci}}} + s \right)^{a_{\text{hb}}}$$

$$(6.10)$$

where  $\sigma_1'$  and  $\sigma_3'$  are the principal effective stresses,  $\sigma_{ci}$  is the uniaxial compressive strength and  $m_b$ , s and  $a_{hb}$  are material constants (Itasca, 2008). These constants can be related to the Geological strength index GSI, the disturbance factor  $D_d$  and the material constant  $m_i$  (Hoek et al., 2002, 1998). With GSI = 90 (depending on friction angle, here  $\phi' = 35^\circ$ , Table 5.1),  $D_d = 0.5$  (average disturbance) and  $m_i = 7$  (for Chalk), the material parameters were determined to  $m_b = 4.3$ , s = 0.26 and  $a_{hb} = 0.5002$ . The value for  $\sigma_{ci}$  was obtained as follows,

$$\sigma_{\rm ci} = \frac{\sigma_{\rm c}}{s^{a_1}} = 7.85 \, MPa \tag{6.11}$$

where  $\sigma_c$  is the unconfined compressive strength, which was measured to be approximately 4 MPa in the Geotechnical Interpretative Report (GIR) (Morgan Sindall, 2012).

The material behaves elastic before yield. After yield the user can decide whether the material coefficients  $\sigma_{ci}$ ,  $m_b$ , s and  $a_{hb}$  remain constant or soften with increasing plastic confining strain. For this study the coefficients remain constant after yield.

## 6.5 Constitutive wall model

In the PLAXIS design the wall was assumed isotropic where the stiffness in circumferential direction is equal to the vertical stiffness. This may not be adequate as discussed in Section 2.4.2.1.

For the parametric study in the FLAC2 model it is necessary to be able to reduce the circumferential stiffness. FLAC does not provide a constitutive model that allows a lower circumferential stiffness; it however provides the option to write a user-defined constitutive model in its own programming language, called FISH (Itasca, 2011a).

The compliance matrix  $[D]^{-1}$  for a material with a stiffness E and a reduced circumferential stiffness  $E_{\theta}$  was derived from Hooke's Law and is shown below,

$$\{\dot{\varepsilon}\} = [D]^{-1} \cdot \{\dot{\sigma}\} = \begin{bmatrix} \Delta \varepsilon_{\rm r} \\ \Delta \varepsilon_{\rm z} \\ \Delta \varepsilon_{\theta} \\ \Delta \varepsilon_{\rm rz} \end{bmatrix} = \begin{bmatrix} \frac{1}{E} & -\frac{\nu_{\rm rz}}{E} & -\frac{\nu_{\theta \rm r}}{E_{\theta}} & 0 \\ -\frac{\nu_{\rm rz}}{E} & \frac{1}{E} & -\frac{\nu_{\theta \rm r}}{E_{\theta}} & 0 \\ -\frac{\nu_{\theta \rm r}}{E_{\theta}} & -\frac{\nu_{\theta \rm r}}{E_{\theta}} & \frac{1}{E_{\theta}} & 0 \\ 0 & 0 & 0 & \frac{1+\nu_{\rm rz}}{E} \end{bmatrix} \cdot \begin{bmatrix} \Delta \sigma_{\rm r} \\ \Delta \sigma_{\rm z} \\ \Delta \sigma_{\theta} \\ \Delta \sigma_{\rm rz} \end{bmatrix} \tag{6.12}$$

where the strain vector  $\{\dot{\varepsilon}\}$  comprises the incremental radial strain  $\Delta\varepsilon_{\rm r}$ , vertical strain  $\Delta\varepsilon_{\rm z}$ , circumferential strain  $\Delta\varepsilon_{\theta}$  and shear strain  $\Delta\varepsilon_{\rm rz}$  and the stress vector  $\{\dot{\sigma}\}$  comprises the incremental radial stress  $\Delta\sigma_{\rm r}$ , vertical stress  $\Delta\sigma_{\rm z}$ , circumferential stress  $\Delta\sigma_{\theta}$  and shear stress  $\Delta\sigma_{\rm rz}$ .  $\nu_{\rm rz}$  is the Poisson's ratio of the material in the plane of isotropy and  $\nu_{\theta \rm r}$  is the value between the anisotropic and isotropic direction.

## 6.6 FLAC runs and parametric study

### 6.6.1 FLAC1

As mentioned previously FLAC1 is a simplified model, similar to the PLAXIS design. The input parameters for the analysis are given in Table 6.4. FLAC requires the dry density  $\gamma_{\rm dry}$  which was obtained through the bulk density  $\gamma_{\rm bulk}$  (Table 5.1) and the porosity from the GIR (Morgan Sindall, 2012). Permeability values could also be estimated from the GIR. All other parameters were the same as in the PLAXIS design with two exceptions: River Terrace Deposits layer was given a dilation angle  $\psi = \phi'/2$  and  $K_0 = 0.6$ . The stratigraphy was slightly altered to match the borehole record.

The wall is modelled as WIP with reduced  $K_0$  values (Table 6.4) to take account for stress relief during wall installation.

The excavation is modelled in steps of 1 m (instead of 10 m as PLAXIS) so that interpolation to the fibre optic (FO) excavation levels is not required.

### 6.6.2 FLAC2

As mentioned above the FLAC2 model was used to carry out a parametric study. Several analyses with varied parameters were conducted. An overview is provided in Table 6.6; further details on the parameters considered is given below:

- **Soil models:** The PLAXIS design assumed MC model for all ground layers. The effect of using advanced soil models, as detailed in Section 6.4, is investigated.
- **Wall installation/ WIP:** It is examined whether modelling the wall installation or assuming a WIP wall has an effect on the results.
- **Wall stiffness:** The PLAXIS design used a short-term Young's modulus of 37 GPa for the C50/60 concrete. Due to creep and relaxation over time a Young's modulus of 26 GPa (70 % of the original value as adivsed by CIRIA C580, Gaba et al., 2003\) was used for a long-term analysis. The FLAC2 model is used to investigate how a reduced Young's modulus influences the results.
- **Wall anisotropy:** As discussed in Section 2.4.2.1, there is a high uncertainty of the wall stiffness in circumferential direction due to the discontinuous nature of diaphragm walls. Several FLAC2 models were run with decreased circumferential stiffness.
- **Wall thickness:** The PLAXIS design assumed a 1.2 m thick ring structure as shaft wall. While the walls are likely to be 1.2 m thick, the verticality tolerance may have reduced the overlap between the panels and hence the thickness of the ring structure. To investigate the impact of a reduced thickness of the ring structure, two models were run: (1) FLAC2-tred with a reduced thickness of 1.0 m (constant over depth) and (2) FLAC2-tvert with full thickness of 1.2 m at the top and 0.9 m at the bottom (Figure 6.6\). This is a conservative simplification, as each panel is in reality still 1.2 m thick and only the overlap is reduced by the verticality tolerances. It was however not possible to model this in a two-dimensional program and hence the real wall thickness, which would be beneficial for the wall's bending stiffness, was neglected.

**Chalk stiffness:** The Chalk stiffness is highly uncertain. The GIR \(Morgan Sindall, 2012\) provides the results of high pressure dilatometer tests which indicate Young's moduli between approximately 500 MPa and 4000 MPa depending on the strain level. The effect of varying the Chalk stiffness between the upper and lower limit is investigated.

**Lateral earth pressure coefficient** *K*<sup>0</sup> **of the Chalk:** The lateral earth pressure in Chalk is also highly uncertain. CIRIA C574 \(Lord et al., 2002\) states that few measurements of horizontal stresses have been made and that design practice usually assumes a *K*<sup>0</sup> between 0.5 and 1.0. However, Watson et al. \(1999\) reports values between 0.5 and 1.5 based on self-boring pressuremeter tests undertaken for the North Downs Tunnel; Rankin and May \(1996\) back-analyses *K*<sup>0</sup> values from the Channel Tunnel up to 1.7. Hence FLAC is run with varying *K*<sup>0</sup> values in the Chalk to investigate the influence of this parameter.

Figure 6.6: Reducing wall thickness due to verticality of panels

## 6.7 Assumptions and limitations

**Uncoupled modelling approach:** A fully coupled model involving real time would not have been feasible due to the long computational time in FLAC. Hence an uncoupled approach was used which assumed that, during the excavation stage, the clayey soil layers are 'undrained' and the sandy soil layers are 'fully drained'. In reality, depending on rate of excavation and permeability of the ground, some soil layers are 'partially' drained.

**Simplified two-dimensional model:** FLAC2D in axisymmetric mode was used. This imposes several limitations:

- It is not possible to account for any non-uniform ground conditions or construction activities (e.g. culvert construction, dewatering trial) and hence investigate three-dimensional deformation.
- In reality the wall installation is carried out panel by panel, while these simulations model the wall installation of all panels at the same time.
- **Concrete wall linear elastic:** The concrete wall was modelled as linear elastic. In reality concrete is non-linear and can crack, which was not included in the model.
- **Soil parameters:** The soil parameters are based on laboratory experiments and previous experience as detailed in the GIR \(Morgan Sindall, 2012\). The wide scatter of some experiments, the not always transferability of empirical data and the spatial variability of parameters and ground layers around the shaft cannot be taken into account.

Table 6.4: FLAC1 input parameters

| Stratum | Top level | $\gamma_{\rm dry}$ | Porosity | Permeability | K | G | ν | $\phi'$ | ψ | <i>c'</i> | $K_0$ |
|---|---|---|---|---|---|---|---|---|---|---|---|
|   | [mbgl] | $[kg/m^3]$ | [-] | [m/s] | [MPa] | [MPa] | [-] | [°] | [°] | [kPa] | [-] |
| MG | 0 | 1654 | 0.35 | $1 \times 10^{-5}$ | 4.2 | 1.9 | 0.3 | 30 | 0 | 0 | 0.5 |
| RTD | 10 | 1654 | 0.35 | $1 \times 10^{-5}$ | 41.7 | 19.2 | 0.3 | 38 | 19 | 0 | 0.6 |
| LC | 13 | 1583 | 0.42 | $1 \times 10^{-8}$ | 38.3 | 28.8 | 0.2 | 25 | 0 | 0 | 1 |
| LGC | 18 | 1642 | 0.36 | $1 \times 10^{-8}$ | 53.3 | 40 | 0.2 | 27 | 0 | 0 | 1 |
| LGS | 28 | 1654 | 0.35 | $1 \times 10^{-6}$ | 44.4 | 33.3 | 0.2 | 40 | 0 | 0 | 1 |
| TS | 36 | 1754 | 0.35 | $1 \times 10^{-6}$ | 187.5 | 86.5 | 0.3 | 40 | 0 | 0 | 1 |
| CH | 50 | 1600 | 0.35 | $1 \times 10^{-6}$ | 1000 | 600 | 0.25 | 35 | 0 | 20 | 1 |

Table 6.5: FLAC2 input parameters

| Stratum | $\gamma_{\rm dry}$ | Porosity | Permeability | Soil | K | G | a | ν | $\phi'$ | ψ | c′ | $K_0$ (WIP) | K <sub>0</sub> (Inst) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|   | $[kg/m^3]$ | [ - ] | [m/s] | model | [MPa] | [MPa] | [ - ] | [-] | [°] | [°] | [kPa] | [ - ] | [ - ] |
| MG | 1654 | 0.35 | $1 \times 10^{-5}$ | MC | 4.2 | 1.9 | - | 0.3 | 30 | 0 | 0 | 0.5 | 0.5 |
| RTD | 1654 | 0.35 | $1 \times 10^{-5}$ | MC | 41.7 | 19.2 | - | 0.3 | 38 | 19 | 0 | 0.6 | 0.6 |
| LC | 1583 | 0.42 | $1 \times 10^{-8}$ | MC* | 107 | 80 | 4500 | 0.2 | 25 | 0 | 0 | 1 | 1.7 |
| LGC | 1642 | 0.36 | $1 \times 10^{-8}$ | MC* | 666.7 | 500 | 18000 | 0.2 | 27 | 0 | 0 | 1 | 2 |
| LGS | 1654 | 0.35 | $1 \times 10^{-6}$ | SHS | 44.4 | 33.3 | - | 0.2 | 40** | 0** | 0 | 1 | 1 |
| TS | 1754 | 0.35 | $1 \times 10^{-6}$ | SHS | 187.5 | 86.5 | - | 0.3 | 40** | 0** | 0 | 1 | 1 |
| CH | 1600 | 0.35 | $1 \times 10^{-6}$ | HB | 1000 | 600 | - | 0.25 | see S | Section | n 6.4.5 | 1 | 1 |

with stiffness degradation parameters change after onset of yield

Table 6.6: Parametric study

|   |   |   | Wall | stiffness | Wall | Chalk |   |
|---|---|---|---|---|---|---|---|
| Run ID | Soil model | WIP/ Inst | E | $E_{\theta}$ | thickness | stiffness | Chalk $K_0$ |
|   |   |   | [GPa] | [GPa] | [m] | [MPa] |   |
| FLAC1 | MC (all layers) | WIP | 37 | 37 | 1.2 | 1500 | 1 |
| FLAC2-B | see Table 6.5 | Inst | 37 | 37 | 1.2 | 1500 | 1 |
| FLAC2-WIP | see Table 6.5 | WIP | 37 | 37 | 1.2 | 1500 | 1 |
| FLAC2-WIP* | see Table 6.5 | WIP* | 37 | 37 | 1.2 | 1500 | 1 |
| FLAC2-Ered | see Table 6.5 | Inst | 26 | 26 | 1.2 | 1500 | 1 |
| FLAC2-A50 | see Table 6.5 | Inst | 37 | 18.5 | 1.2 | 1500 | 1 |
| FLAC2-A10 | see Table 6.5 | Inst | 37 | 3.7 | 1.2 | 1500 | 1 |
| FLAC2-A100-10H | see Table 6.5 | Inst | 37 | 37⊳3.7(84)* | 1.2 | 1500 | 1 |
| FLAC2-A10-100H | see Table 6.5 | Inst | 37 | 3.7⊳37(84)* | 1.2 | 1500 | 1 |
| FLAC2-A10-100H/3 | see Table 6.5 | Inst | 37 | 3.7⊳37(27)* | 1.2 | 1500 | 1 |
| FLAC2-A50-100H/3 | see Table 6.5 | Inst | 37 | 18.5⊳37(27)* | 1.2 | 1500 | 1 |
| FLAC2-A50-100-5m | see Table 6.5 | Inst | 37 | 3.7⊳37(5)* | 1.2 | 1500 | 1 |
| FLAC2-Amob | see Table 6.5 | Inst | 37 | $3.7 \triangleright 37(5 \mathrm{mm})^{**}$ | 1.2 | 1500 | 1 |
| FLAC2-tred | see Table 6.5 | Inst | 37 | 37 | 1.0 | 1500 | 1 |
| FLAC2-tvert | see Table 6.5 | Inst | 37 | 37 | 1.2 > 0.9 | 1500 | 1 |
| FLAC2-E4000 | see Table 6.5 | Inst | 37 | 37 | 1.2 | 4000 | 1 |
| FLAC2-E500 | see Table 6.5 | Inst | 37 | 37 | 1.2 | 500 | 1 |
| FLAC2-Ko0.5 | see Table 6.5 | Inst | 37 | 37 | 1.2 | 1500 | 0.5 |
| FLAC2-Ko1.5 | see Table 6.5 | Inst | 37 | 37 | 1.2 | 1500 | 1.5 |
| FLAC2-Ko0.5WIP | see Table 6.5 | WIP | 37 | 37 | 1.2 | 1500 | 0.5 |
| FLAC2-Ko1.5WIP | see Table 6.5 | WIP | 37 | 37 | 1.2 | 1500 | 1.5 |

<sup>\*</sup> Linear varying, e.g.  $3.7 \triangleright 37(27 \text{ m}) = 3.7 \text{ GPa}$  at top of wall and 37 GPa at 27 mbgl in the wall \*\* Initially 3.7 GPa, linearly increasing to 37 GPa at 5 mm lateral wall movement

# Chapter 7

#### Parametric study and discussion

## 7.1 Overview

This chapter presents the results of the parametric study in FLAC. The aim was to match the measured data and to understand the shaft's performance. As detailed in Section 6.6.2 the influence of several parameters on the structural behaviour (Section 7.2\) and ground movements (Section 7.3\) were investigated.

## 7.2 Structural performance

### 7.2.1 Simple versus advanced constitutive models

This section examines the effect of the soil models. The model FLAC1 is similar to the PLAXIS design, using Mohr-Coulomb (MC) soil model and a wishedin-place (WIP) wall (Table 6.6\). The excavation was carried out in steps of 1 m instead of 10 m as done in PLAXIS (hence no interpolation between excavation levels is necessary when comparing to the field data).

The model FLAC2-WIP does not use MC soil model for all layers; the soil models used for each layer and the parameters are given in Table 6.5 and Section 6.4. Everything else is the same as in FLAC1 (Table 6.6\).

Firstly, the incremental and absolute curvatures/ bending moments from both runs are compared to the fibre optic (FO) measurements (Figures 7.1 and 7.2\). It can be seen that both analyses are quite similar and match the FO data well for shallower excavation levels (Figures 7.1a, 7.1b, 7.2a and 7.2b\). For deeper excavation levels (Figures 7.1d, 7.1e, 7.2d and 7.2e\) it is obvious that FLAC2-WIP matches the FO measurements much better than FLAC1.

Figure 7.2 also contains the reinforcement capacity (dashed blue lines) which was designed according to the ultimate limit state (ULS) bending moments. It can be seen that the measured curvatures/ bending moments can be carried by the existing reinforcement and that the structure is safe.

When comparing the wall deflections with the inclinometer measurements (Figure 7.3\), it can be observed that FLAC1 and FLAC2-WIP are similar at shallow excavation levels above the Chalk (Figures 7.3a to 7.3e\). When excavating in the Chalk, FLAC2-WIP exhibits a sharper bulge at excavation level in comparison to FLAC1, which agrees well with the inclinometer measurements (Figures 7.3f to 7.3h\). The sharper bulge also explains why larger curvatures/ bending moments were measured (Figures 7.1d and 7.1e\).

It appears that the field measurements in the Chalk are better represented with FLAC2-WIP, which used the Hoek-Brown (HB) model for the Chalk instead of the MC model. The reason for this is discussed in Figure 7.4. The shear yield envelopes for both soil models according to Equations 6.1 and 6.10 are plotted in Figure 7.4a. This shows that the soil simulated with the HB model allows larger stress states before the onset of yield. The stress states in the elements below excavation level are also plotted, and it can be seen that FLAC1 stress states are on the MC failure envelope. This is also shown in Figure 7.4b where the plasticity indicator is plotted on the FLAC grid. Most elements up to 20 m below excavation level are currently at yield or have been at yield in the past. The same plot for FLAC2-WIP (not displayed) shows that the elements are still elastic, as also shown in Figure 7.4a, where the stress states are far below the failure envelope. This suggests that the larger curvatures/ bending moments and the sharper bulge in the wall arise from the fact that the soil below excavation level remained elastic, not plastic, and is hence less deformable.

The MC failure envelope is determined by the cohesion intercept *c* ′ and the effective stress friction angle *φ* ′ . The Geotechnical Interpretative Report (GIR) \(Morgan Sindall, 2012\) which is based on CIRIA C574 \(Lord et al., 2002\) recommends *c* ′ = 20 kPa and *φ* ′ = 39° as a 'moderately conservative' approach for structured chalks of grades A to C. Since the majority of Chalk at Abbey Mills was classified into grades A2-A4 (according to CIRIA C574's grading scheme in Section 3.3.3, Lord et al., 2002\) the moderately conservative values were deemed on the 'safe side'. However, in this case the moderately conservative cohesion value predicted smaller wall bending moments than occurred in reality. This shows that assigning a low cohesion to induce conservative ground movements may not always be appropriate for the wall design.

Figure 7.1: FLAC's predictions on the effect of soil models on incremental curvature/ bending moment in comparison with FO measurements

Figure 7.2: FLAC's predictions on the effect of soil models on absolute curvature/ bending moment in comparison with FO measurements

Figure 7.3: FLAC's predictions on the effect of soil models on lateral wall movement in comparison with inclinometer data

(a) Shear failure envelopes of MC and HB model with stress states in soil below excavation level

(b) FLAC1 model with plasticity indicator for grid elements

Figure 7.4: Investigating the difference between MC and HB model for Chalk

### 7.2.2 Effect of wall installation versus WIP assumption

Three models were run to investigate whether the excavation-induced numerical predictions are influenced by the wall installation: FLAC2-B, FLAC2-WIP and FLAC2-WIP\* (Table 6.6\).

FLAC2-B which includes the full wall installation as detailed in Section 6.3. The lateral earth pressure coefficients *K*<sup>0</sup> for all ground layers can be found in Table 6.5 and are plotted on the graph in Figure 7.5a.

In design practice, it is quite common to neglect the wall installation and assume a WIP wall; in this case the lateral earth pressure coefficients are reduced to account for the stress relaxation during wall installation. Two WIP analyses are run, FLAC2-WIP and FLAC2-WIP\*; the former uses the *K*<sup>0</sup> values as given in the PLAXIS design (Table 6.5\) which are based on the recommendations in the GIR \(Morgan Sindall, 2012\). The latter is based on *K*<sup>0</sup> values determined from FLAC2-B after wall installation from the stresses in an element 2.5 m away from the wall (average between soil and excavation face). All *K*<sup>0</sup> profiles are plotted in Figure 7.5a. It is noted that the *K*<sup>0</sup> values of FLAC2-WIP\* are relatively high in comparison to FLAC2-B, against the common assumption that wall installation reduces the lateral earth pressure. This is due to the large horizontal forces from the wet concrete which is based on a density of 23 kN/m<sup>3</sup> .

The results in terms of lateral wall movement, incremental and absolute curvature/ bending moment are displayed in Figures 7.5b to 7.5d, respectively. It can be seen that the difference is insignificant and that all three analyses give very similar results. This shows that the WIP assumption is reasonable when modelling excavation-induced structural movements and forces. However, modelling the wall as WIP does not allow to predict ground movements caused by the wall installation, which may be larger than excavation-induced movements, as shown in Section 5.4.

Figure 7.5: FLAC's predictions on the difference between WIP or full wall installation

### 7.2.3 Effect of wall stiffness and anisotropy

Table 6.6 provides on overview of the FLAC models run to examine the wall's anisotropy (i.e. reduced circumferential stiffness due to the effect of the joints between the panels). While FLAC2-Ered is based on an isotropic wall with 30 % stiffness reduction, the other analyses incorporate anisotropy. The vertical stiffness is kept constant at *E* = 37 GPa and the circumferential stiffness *E*θ is reduced to either constant or linear distributions over wall depth, as displayed in Figure 7.6. The model FLAC2-A100-10H (full stiffness at top, 10 % at bottom) was used to simulate verticality tolerances where the overlap between the panels and hence potentially the hoop stiffness reduces with depth. The model FLAC2-A10-100H assumes 10 % stiffness at the top and 100 % at the bottom, which may be the case as lower confining pressures may result in lower circumferential stiffness. The other models with a partly linear and partly constant circumferential stiffness were run to investigate whether low hoop stiffness at the top can simulate cantilever movement, as observed in Figure 5.4. One FLAC model (FLAC2-Amob) is based on an initial hoop stiffness of 10 % *E* linearly increasing to 100 % *E* at 5 mm lateral wall movement.

Figure 7.6: Circumferential stiffness versus wall depth for FLAC runs with anisotropic wall stiffness

#### Parametric study and discussion

The results in terms of incremental curvature/ bending moment are presented in Figure 7.7, lateral wall displacement in Figure 7.8 and hoop strain in Figure 7.9.

From the incremental curvatures (Figure 7.7\) it can be observed that the analyses with lowest circumferential stiffness at the top of the wall (FLAC2- A10, FLAC2-A10-100H, FLAC2-A10-100H/3, FLAC2-A10-100-5m) give largest values, while the model run FLAC2-A100-10H which has 100 % hoop stiffness at the top of the wall and 10 % at the bottom gives almost the same as the isotropic wall.

Similar trends, even more obvious, can be observed from the lateral wall movements (Figure 7.8\). The two runs with 50 % hoop stiffness at the top also show alike behaviour, even though the stiffness at deeper depth is different. When comparing the run with 100 % stiffness at the top and 10 % at the bottom to the isotropic wall, hardly any differences can be observed. This shows clearly that the stiffness at the top of the wall governs its performance. The low stiffness allows more rotation of the wall head, which causes a significant increase in lateral wall movement. The run taking mobilisation into account, FLAC2-Amob, also overestimates the wall's lateral movement. It is difficult to determine the input parameters for this model, which are the initial hoop stiffness and the lateral wall movement when full stiffness is mobilised.

The hoop stresses in Figure 7.9 directly relate to the wall deflection in Figure 7.8. Hence, the small increases in wall movement in the Chalk do not significantly affect the hoop strain at around 60 mbgl (Figure 7.9a\). For panel P15, in which the hoop strain was measured at a higher level, the anisotropy has a considerable effect, as the wall movements are as large as 20 mm.

Figure 7.9 also includes the range of FO measurements. It may be difficult to compare the FO measurements of panels P10 and P20 due to the potential creep influence which caused the early increase in hoop strain. Hence the FO data from panels P10 and P20 is baselined with the 15 mbgl dataset and also added to the figure (Figure 7.9a\). All FLAC predictions are within the range of FO measurements. Due to the wide scatter of FO data it is difficult to draw conclusions. The FO measurements from panel P15, which were not affected by creep are plotted in Figure 7.9b. Only the isotropic wall with full stiffness (37 GPa) and reduced stiffness (26 GPa) and the wall with linear decreasing stiffness (from 100 % at top of wall to 10 % at bottom) match the FO data well.

Figure 7.7: FLAC's predictions on the effect of wall stiffness/anisotropy on incremental curvature/ bending moment in comparison with FO measurements

Figure 7.8: FLAC's predictions on the effect of wall stiffness/ anisotropy on lateral wall movement in comparison with inclinometer data

Figure 7.9: FLAC's predictions on the effect of wall stiffness/ anisotropy on hoop strain in comparison with FO data

Taking all field data into account it seems most likely that the wall behaved fully isotropically due to the following reasons:

- In Figures 7.7a to 7.7c curvatures are significantly overestimated by the FLAC runs with 10 % stiffness at the top, as well as the model that considered the mobilisation. The FO measurements from panels P15 and P20 at deeper levels (Figures 7.7d and 7.7e\) differ from each other too much to allow a reliable conclusion.
- The wall deflection plots in Figure 7.8 seem to match best with the isotropic wall or the wall with linear variation from 100 % at the top to 10 % at the bottom. The FLAC runs with 50 % at the top overestimate the movement and are hence not considered the correct mechanism.
- The isotopic wall also matches the hoop profile of panel P15 in Figure 7.9b well and is within the FO measurement range (baselined at 15 mbgl) from panels P10 and P20 Figure 7.9a.

Since the isotropic wall and the wall with full stiffness at the top reducing to 10 % at the bottom (FLAC2-A100-10H) give the same results, it is reasonable to assume isotropic conditions.

#### Parametric study and discussion

The conclusion of isotropic wall stiffness also seems reasonable when considering the joint construction at Abbey Mills (Figure 7.10). After all primary panels were built the secondary panels were constructed. The hydrofraise cut into the concrete of the primary panels (this is easily possible with the more powerful hydrofraise) and when the secondary panels were concreted, direct contact was guaranteed. When considering plane strain excavations made of diaphragm walls (e.g. Figure 7.11), where out of plane bending moments might open up the joints between the panels, anisotropy is a reasonable assumption. In circular excavations however there is reason for joints opening up.

As discussed in Section 5.3.2.2 the wall might have undergone a small cantilever movement at early excavation stages. It was aimed to represent this numerically with FLAC through wall anisotropy, as proposed by Cabarkapa et al. (2003). Even the wall which had 10 % hoop stiffness at the top increasing to full stiffness at 5 mbgl (FLAC2-A10-100-5m) did not show cantilever movement without also increasing the movements at depths. The cantilever movement measured at Abbey Mills might not be uniform around the shaft (this seems also unreasonable due to the stiff capping beam); potentially a small ovalisation has taken place as discussed in Section 5.3.2.3.

Figure 7.10: Construction of joint between diaphragm wall panels at Abbey Mills shaft

Figure 7.11: Rectangular excavation made from diaphragm walls and reason for anisotropy

### 7.2.4 Effect of wall thickness and verticality

Two analyses were run to investigate the effect of reduced wall thickness with depth due to verticality (Table 6.6\): (1) the overall wall thickness was reduced to 1.0 m and (2) the wall thickness was decreased linearly from 1.2 m at the top to 0.9 m at the bottom - this corresponds to a verticality of 1:400 in one direction and 1:800 in the other direction (Figure 6.6\).

The results are compared to the baseline FLAC run with a wall thickness of 1.2 m (FLAC2-B). Figure 7.12 displays the lateral wall movement and incremental and absolute curvature of the three FLAC simulations.

The wall deflections for thinner walls (Figure 7.12a and Table 7.1\) only increase slightly, even though the bending stiffness reduces significantly for the thinner walls. This shows that *EI* has a minor effect on the wall deflection as reported by Lam \(2010\) and Bolton et al. \(2010\) for non-circular excavations (Section 2.3.5\).

It can also be observed that the thinner walls generate slightly larger curvatures Figures 7.12b and 7.12c. However, due to the reduced bending stiffness *EI* of the thinner walls the slightly larger curvatures translate into smaller bending moments. The calculations in Table 7.1 show that even though FLAC2-tvert yields the largest curvature, the bending moment is the smallest.

When comparing the FLAC results to the field measurements, it is not possible to derive if verticality had an influence due to the uncertainty inherent to the inclinometer data and the small differences in the FLAC outputs.

The results raise the question whether a thinner wall (1 m instead of 1.2 m) would have been feasible. If structural and ground movements are the decisive factor (e.g. to protect adjacent infrastructure), thinner walls can be considered.

Table 7.1: FLAC's predictions of maximum wall deflection, curvature and bending moment for different wall thickness (Equation 3.10)

| FLAC run | t<br>[m] | EI<br>[MNm <sup>2</sup> ] | $\Delta u_{\text{max}}$ [mm] | $\frac{\Delta \kappa_{\text{max}}}{[10^{-4} \text{m}^{-1}]}$ | $\Delta BM_{\rm max}$ [MNm] |
|---|---|---|---|---|---|
| FLAC2-B | 1.2 | 5328 | 3.4 | 0.76 | 4049 |
| FLAC2-tred | 1.0 | 3083 | 4.0 | 0.96 | 2960 |
| FLAC2-tvert | 0.95* | 2614 | 3.9 | 1.10 | 2875 |

<sup>\*</sup> thickness at depth of maximum curvature (71 mbgl)

For Abbey Mills shaft however high compressive stresses were caused by the tunnel openings; at the crown and the bottom of the opening values increased by approximately three times. To resist the generated stresses a wall thickness of 1.2 m was required for the design concrete compressive strength  $f_{\rm cd}$  = 28 MPa to be sufficient to resist the large stresses.

Another factor to take into consideration is that thinner walls increase the amount of reinforcement to withstand the same bending moment. Eurocode 2 (British Standards Institution, 1992) imposes requirements on the reinforcement design, such as spacing between bars to guarantee good concrete flow and to avoid inclusions, which may not make thinner walls possible.

Figure 7.12: FLAC's predictions on the effect of wall thickness

### 7.2.5 Effect of Chalk stiffness

The effect of the Chalk stiffness was investigated and the results are shown in Figure 7.13. Two FLAC analyses were run: (1) with an increased Young's modulus of 4000 MPa and (2) with a decreased Young's modulus of 500 MPa (Table 6.6). It can be seen that this has an effect on the wall movement (Figure 7.13a), where the analysis with large stiffness gives very small movements in the Chalk and the analysis with lower stiffness shows the opposite. The maximum wall movement of approximately 4 mm is however not affected significantly.

From Figure 7.13a it seems most appropriate that the stiffness was between 500 and 1500 MPa. The lower stiffness also gives slightly larger incremental curvatures/ bending moments (Figures 7.13b and 7.13c) which matches the FO measurements better. However, the scatter of the monitoring data does not allow to draw reliable conclusions.

Figure 7.13: FLAC's predictions on the effect of Chalk stiffness

### 7.2.6 Effect of lateral earth pressure coefficient of the Chalk

This section aims to compare the FLAC runs with varying *K*<sup>0</sup> values to the field measurements. Set 1 of analyses considers three *K*<sup>0</sup> values of the Chalk: 0.5, 1.0 and 1.5 (Figure 7.14\) and modelled the wall installation (FLAC2-Ko0.5, FLAC2-B, FLAC2-Ko1.5). In set 2 the same *K*<sup>0</sup> values are used but the wall was modelled as WIP (FLAC2-Ko0.5WIP, FLAC2-WIP, FLAC2-Ko1.5WIP, see Table 6.6\). The results of all six FLAC runs in terms of lateral movement, incremental and absolute curvature are shown in Figures 7.15a to 7.15c for set 1 and in Figures 7.15d to 7.15f for set 2.

When the wall installation is modelled the *K*<sup>0</sup> value, if picked between 0.5 and 1.5, does not have a significant influence on the results (Figures 7.15a to 7.15c\). The reason is explained in Figure 7.14; it shows the horizontal pressures in the elements next to the wall in the Chalk after the wall installation, as well as the initial values before wall installation. It can be seen that, almost independent on the initial value, the wall installation causes very similar horizontal stresses. This means any 'mistake' in the *K*<sup>0</sup> value can be compensated when modelling the wall installation.

However, design often assumes a WIP wall where a reduced *K*<sup>0</sup> value (taking the wall installation into account) is applied. In this case the earth pressure coefficient has a significant influence, as can be seen in Figures 7.15d to 7.15f. The *K*<sup>0</sup> = 1.5 results do not match the wall deflection profiles (Figure 7.15d\) and the *K*<sup>0</sup> = 0.5 results reduce the curvature below the FO measurement. Hence, the assumption of *K*<sup>0</sup> = 1.0 seem reasonable.

Figure 7.14: Pressure in elements next to shaft wall for different *K*<sup>0</sup> values of the Chalk before and after wall installation

Figure 7.15: FLAC's predictions on the effect of the lateral earth pressure coefficient in Chalk

## 7.3 Ground movement

### 7.3.1 Shaft excavation

This section compares the measured ground movement during shaft excavation with the numerical and empirical predictions.

As detailed in Section 5.3.4.1, the surface measurement pins might have been influenced by site traffic and might not properly represent excavation-induced surface settlement. The survey furthermore only started at an excavation level of 20 mbgl and hence does not provide surface settlement at shallow excavation levels. It does however show that the movements were small. As approximation of the surface settlement the highest anchors of the rod extensometers (at around 8 mbgl) are used. Figure 7.16 includes the settlements of the extensometers AE1 and BE1 (2.5 m distance from shaft wall) and AE2 and BE2 (6 m distance from shaft wall) from Figure 5.11. The recorded settlements during shaft excavation were very small, less than 1.5 mm.

The empirical predictions from Equations 2.2 and 2.5, by New and Bowers \(1994\) and Geotechnical Consulting Group \(2007\) respectively applied to Abbey Mills shaft, are also plotted in the figure. New and Bowers \(1994\) predict a maximum settlement of 41 mm next to the shaft wall and an extent of the trough of 70 m. Geotechnical Consulting Group \(2007\) predicts even larger settlement and extent of the trough (Figure 7.16\). This is due to the inclusion of the diameter in Equations 2.3 and 2.4, which is neglected by New and Bowers \(1994\). When comparing to the measurements it is obvious that both formulas overestimate the settlement significantly.

The numerical predictions from FLAC and PLAXIS are also considered in Figure 7.16. FLAC and PLAXIS both predict heave of approximately 5 mm next to the shaft wall during the excavation. The explanation for this can be found in Figure 7.17 which plots the displacement vectors of the FLAC model. Due to removal of overburden pressure the excavation surface heaves 13.9 mm. This causes the diaphragm wall, as well as the surrounding ground, to move upwards. According to FLAC the top of the wall heaves 4.9 mm. The level measurements of the diaphragm wall targets (Section 5.3.2.3, Figure 5.8\) confirm this mechanism, but measures slightly larger values between 7 and 11 mm.

The displacement vectors also explain why the rod extensometer measured hardly any vertical movement during shaft excavation: The soil body behind the wall was moving upwards as a whole, including the bottom anchor which was assumed stable to act as reference for the other anchors of the same rod extensometer (Section 4.2.1\). This means that the rod extensometer data presented in Figure 5.11 does not show absolute but relative movement between the bottom anchor and the anchors above. Instead of using the bottom anchor as reference, it would have been better to use a borehole head survey. At Abbey Mills this data was however not accurate enough to do so.

Since numerical predictions and diaphragm wall level movements agree reasonably well, it seems likely that the maximum heave next to the diaphragm wall was between 5 and 11 mm. The soil body moved as a whole, as can be seen from the rod extensometers, which show hardly any differential movement between the bottom anchor and the anchors above (Figure 5.11\).

The predictions of horizontal ground movements during shaft excavation in comparison with the inclinometer data are displayed in Figures 7.18 and 7.19, where Figure 7.18 presents the inclinometer data from AE2 and BE2 6 m behind the shaft wall; Figure 7.19 inclinometers AE3 and BE3 in 15 m distance from the shaft wall (for plan view see Figure 3.2\).

The measured and predicted ground movements are very small and match reasonably well for shallow to medium deep excavation levels (Figures 7.18a to 7.18e and 7.19a to 7.19f\). While a subsurface bulge forms, hardly any movement is measured at the surface. A kink develops at the interface of the Thanet Sand and the Chalk.

When the excavation level exceeds the depth of the borehole, the bottom of the inclinometer, which is usually assumed fixed, moves towards the excavation (Figures 7.18f to 7.18h, 7.19g and 7.19h\). Hence, it was not possible to biascorrect the data. Therefore it is less reliable; the shape of the data however matches the FLAC predictions well and hence confirms its validity.

Overall, the movements are very small and do not exceed 2 mm.

Figure 7.16: Empirical formulas by New and Bowers (1994) and Geotechnical Consulting Group (2007) applied to Abbey Mills shaft in comparison with highest rod extensometer sensors and PLAXIS and FLAC predictions

Figure 7.17: FLAC's predictions of excavation-induced ground displacement

⚠= Bias correction not possible (excavation depth exceeds borehole depth)

Figure 7.18: FLAC's predicted horizontal ground movements in comparison to inclinometer measurements AI2 and BI2 6 m behind shaft wall

Figure 7.19: FLAC's predicted horizontal ground movements in comparison to inclinometer measurements AI3 and BI3 15 m behind shaft wall

= Bias correction not possible (excavation depth exceeds borehole depth)

### 7.3.2 Diaphragm wall construction

Figure 7.16 also includes the rod extensometer measurements from the highest anchor during wall installation as well as FLAC's prediction. The rod extensometers measured settlements between 2 and 5 mm, while FLAC predicts large heaves of up to 35 mm, which appears unrealistic. Figure 7.20 presents the displacement vectors during wall installation as predicted by FLAC. In the first step of wall installation the bentonite pressure is applied to the trench/ soil interface (Figure 6.2\); this causes large settlements (up to 90 mm, as shown in Figure 7.20a\). When then the wet concrete pressure acts against the interface, the shallow ground is pushed upwards and away from the trench (maximum values are 127 mm, as shown in Figure 7.20b\).

These values appear unrealistically large. It seems that the large movements are related to the numerical assumptions. In the two-dimensional axisymmetric simulation all panels are excavated at the same time, while in reality the wall is made of individually constructed panels. Constructing panel by panel allows beneficial arching effects to develop and reduces ground movement.

Figure 7.20: FLAC's predictions of ground displacement during diaphragm wall installation

## 7.4 Summary of key findings

**Soil model Chalk/ low cohesion:** The curvature/ bending moment measurements in the wall in the Chalk exceeded the predictions. It was shown that this is related to the modelling assumptions of the Chalk. The PLAXIS design used the MC soil model with a low cohesion to induce conservative estimates on ground movements. This low cohesion value caused the soil to yield under low stresses. In reality the soil remained elastic and induced larger bending moments in the wall.

**WIP assumption:** The excavation-induced structural results were not affected by the method of wall installation. Hence, the WIP assumption is reasonable, but cannot provide ground movements during diaphragm wall installation.

**Wall anisotropy:** The FLAC results in comparison with the field data suggest that the Abbey Mills diaphragm wall shaft behaved isotropically, as opposed to suggestions by previous researchers \(Cabarkapa et al., 2003; Zdravkovic et al., 2005\) that the circumferential stiffness has to be reduced to account for the joints between the panels. This may be related to the construction method of the joints between the panels (cutting into the adjacent panel with the hydrofraise), which guaranteed a strong and stiff connection. Further studies are necessary to confirm whether full circumferential stiffness can be assumed for all diaphragm wall shafts of if the joint construction method has an influence. The simulations also showed that anisotropy at the top of the shaft wall, if existing, has a major impact on structural and hence ground movements.

**Wall thickness:** The wall thickness has a minor effect on the maximum lateral wall deflection. Thinner walls might be possible, provided that this design complies with the requirement of Eurocode 2 and the increased reinforcement fits into the reduced width.

**Chalk stiffness:** The comparison of field data and numerical results suggests that the stiffness of the Chalk at Abbey Mills (grades A2-A4 according to CIRIA C574's grading scheme, Lord et al., 2002\) is between 500 and 1500 MPa.

- **Lateral earth pressure coefficient in the Chalk:** The *K*<sup>0</sup> value assigned to the Chalk does not have a significant influence on structural forces and deformations if the wall installation is modelled. If the WIP wall assumption is used, *K*<sup>0</sup> significantly influences the results and a value of 1.0 best matches the field data.
- **Surface settlement:** Empirical formulas predict very large settlements around the shaft while monitoring data showed very small movements. Hence, New and Bowers' \(1994\) formula cannot be transferred to excavations of different geometries, construction methods and ground conditions.
- **Rod extensometer assumption:** For the rod extensometer analysis the bottom anchor was assumed stable. This was probably not the case as the removal of overburden pressure inside the shaft caused the wall and the ground behind the wall to move upwards. For future monitoring schemes, it is necessary to conduct a more accurate borehole head survey.
- **Wall installation modelling assumption:** It also appears that modelling the wall installation in two-dimensional axisymmetric mode significantly overestimates the ground movement due to the negligence of the soil arching effects.

# Chapter 8

## Summary and conclusion

## 8.1 Summary

In congested cities, tunnels and deep excavations are often built in sensitive areas adjacent to existing infrastructure. This imposes very tight restrictions on structural and ground movements to protect buildings and services. While tunnels and rectangular excavations have been researched extensively, little attention has been paid to circular shafts. As detailed in Chapter 2, the limited number of existing case studies makes it difficult to use empirical evidence to estimate ground and structural movements, as advised by codes and standards. Current British design practice frequently refers to one case study by New and Bowers \(1994\). Although this study was derived under specific conditions, the results are applied to other projects with different geometries, ground conditions and construction methods. Due to this high uncertainty conservative approaches are adopted which may lead to more expensive structures and protective measures.

On the other hand, the design assumptions for diaphragm wall shafts may underestimate movements by adopting isotropic wall stiffness. Walls may not behave isotropically due to the joints between the individual panels, which may cause a lower circumferential stiffness. Anisotropy would have a crucial impact on the wall deflections of circular excavations, which mainly rely on the development of hoop stresses.

To address these uncertainties, a large monitoring scheme was implemented at Thames Water's Abbey Mills Shaft F in East London. The instrumentation comprised fibre optic (FO) strain and temperature sensors, inclinometers, extensometers and optical surveys to measure structural performance of the diaphragm wall, as well as ground movements around the excavation. Chapter 3 detailed the installation procedure and data analysis of the FO instrumentation, while Chapter 4 focused on the conventional instrumentation and the optical surveys.

The monitoring results in comparison with the initial PLAXIS design predictions were presented in Chapter 5. An emphasis was placed on the excavation-induced measurements, but results from the diaphragm wall construction, the dewatering trial prior to shaft excavation and the annulus infill were also reported.

A further numerical investigation was conducted in FLAC which allowed a more flexible parametric study. The modelling procedure, the constitutive soil and wall models and an overview of the parametric study were detailed in Chapter 6. Several FLAC models were run to investigate the influence of the following parameters on structural movement and forces: soil models, wall installation, wall stiffness and anisotropy, wall thickness, Chalk stiffness and lateral earth pressure coefficient in the Chalk. The results in comparison to the field data were presented in Chapter 7.

## 8.2 Main findings

### 8.2.1 Field instrumentation

#### Fibre optic instrumentation

FO cables were, for the first time, installed in very deep diaphragm wall panels, which was especially challenging as the cables had to be bridged over the reinforcement cage splices. With the help of the Fujikura pretension clamp it was possible to attach the FO cables quickly during the cage installation, without interrupting it.

The data analysis incorporated an auto-correlation algorithm which improved the FO results. Small misalignments in the raw data induced by breakages/ repairs, splices or the distance inaccuracy of the read-out unit could be compensated.

For future installations it is important to take measures to avoid breakages in the FO cables. The bending strain cable (BSC) should be attached loosely to the longitudinal reinforcement bars with cable ties; this prevents the cable from getting pushed closer to the concrete/ soil interface. Sharp bends in the FO cable can significantly reduce the data quality; it is thus advised to be very careful that loose FO cables have no chance to bend (always guide loose cables along reinforcement bars or support with strong wire).

#### Conventional instrumentation

When small movements are expected, instruments are often not accurate enough to measure these and errors accumulate. This appeared to be the case for the inclinometer data at first sight. However, a comprehensive error correction procedure significantly improved the results and provided more consistent and useful data.

To avoid errors in the inclinometer data in the future, the casing should be installed as straight as possible. When the casing is grouted there are high uplift forces acting against it. The worst way of counteracting is restraining the top, as this causes buckling. Several better ways are suggested by the inclinometer manufacturer Slope Indicator \(2009\). The inclinometer boreholes at Abbey Mills did also not reach deep enough to allow bias error correction for excavation levels below the inclinometer toe. Slope Indicator \(2011b\) advises to extend the casing into stable ground where no movements are expected.

The rod extensometers are very accurate and measure sub-millimetre movements, but require a boundary condition of known movement. At Abbey Mills the optical borehole head survey was not accurate enough to provide the boundary condition. Assuming a stable bottom anchor, as done in this study, might not always hold true. It is thus essential to conduct an accurate and frequent borehole head survey.

Due to the small movements experienced at Abbey Mills the magnet extensometers did not provide good enough resolution.

The optical surface survey only started when the excavation had already reached 20 mbgl and did thus not capture movements prior to this. It was also suspected that the survey measured settlement caused by site traffic instead of the shaft excavation, as the targets were road nails drilled into the concrete platform. Instead 2 to 3 m long steel rods should be driven into the ground and protected with a pipe or a manhole (according to Dunnicliff, 1988, p. 209).

### 8.2.2 Field data

The overall horizontal ground movement was very small with approximately 2 mm during shaft excavation. Rod extensometers measured subsurface ground movement during excavation of around 1 mm. The validity of these measurements is however constrained due to a missing boundary condition, as described below in Section 8.2.3. The optical survey, which started late and was influenced by site traffic, measured settlements up to 3 mm.

During diaphragm wall construction the rod measurements recorded settlements around 6 mm. The dewatering trial did not cause any measurable ground movements, as water levels on the outside of the shaft were not affected. The annulus infill generated small heaves of around 1 mm.

The wall deflection was less than 4 mm during shaft excavation. The annulus infill pushed the diaphragm wall away in the opposite direction by approximately 2.5 mm.

The measured bending strain converted into bending moment was approximately ± 800 kNm during shaft excavation. Slightly smaller magnitudes were measured during the annulus infill.

The FO hoop strain measurements indicated that creep may have occurred in the Chalk which may have increased the earth pressures on the wall during excavation. The measurements further suggest that differential water pressures inside the shaft during the dewatering trial may have caused a three-dimensional deformation of the wall.

### 8.2.3 Field data in comparison

The field measurements during the excavation stage were compared to the initial PLAXIS design predictions and to the results of a parametric study conducted with FLAC.

When comparing the wall's bending moment measurements to the PLAXIS design predictions it was found that these were exceeded. With further numerical investigations in FLAC it was shown that this was related to the low cohesion value assumed for the Chalk in the design stage. In the analysis the Chalk yielded, while in reality the soil seemed to have remained elastic and hence induced larger bending moments in the diaphragm wall than predicted. For future designs, the cohesion value of the Chalk has to be picked carefully. It is recommended to investigate the effect of a low and a high cohesion on the

wall bending moment.

Several studies propose that diaphragm wall shafts have a reduced circumferential stiffness due discontinuous nature of the wall made of individual panels. This study found that the Abbey Mills shaft behaved isotropically, with no stiffness reduction in hoop direction. The way the joints were constructed (cutting into the adjacent panel with a hydrofraise) created a very stiff connection between adjacent panels. Due to the confining earth pressures the joints cannot open up, as it would be the case in a rectangular excavation.

The numerical simulation has shown that the wall bending stiffness has a minor influence on the lateral wall movement and the bending moments. In future designs, where structural and ground movements are the determining factor for the wall thickness, it might be possible to reduce the thickness, provided that this design complies with the requirement of Eurocode 2 and the increased reinforcement fits into the reduced width.

The PLAXIS design modelled the wall as wished-in-place (WIP) and used a lateral earth pressure coefficient of 1.0. The parametric study showed that these assumptions were reasonable to simulate the excavation-induced wall deflections and forces. The WIP assumption does however not provide ground movements during the diaphragm wall installation. When the wall installation is modelled, ground movements can be obtained, but it was found that these are unrealistically large due to the two-dimensional axisymmetric model. When ground movements during wall installation need to be modelled realistically, a three-dimensional model is required, so that each panel's installation can be simulated separately.

The rod extensometer measurements showed minimal settlement during shaft excavation (less than 1.5 mm), assuming a stable bottom anchor. The numerical simulations and the diaphragm wall optical survey demonstrated that the removal of overburden pressure on the excavation surface caused heaves of the wall and the ground behind, limiting the validity of the rod extensometer measurements as the bottom anchor most likely moved. Under greenfield conditions (without traffic on the concrete platform) it would be expected that the soil behind the wall heaves between 5 and 11 mm, based on the numerical predictions and the optical survey of the wall head. The empirical formulas by New and Bowers \(1994\) and Geotechnical Consulting Group \(2007\) on the other hand predict large settlements in the order of 40 to 105 mm. This clearly shows the conservatism of these empirical formulas when being transferred to projects with different conditions.

### 8.2.4 Implications

The findings of this work have several practical implications for the design of deep circular excavations:

1. When designing excavations in Chalk careful consideration has to be given to the Chalk cohesion value, as assuming a low conservative value might induce large bending moments in the wall. Hence it is advised to run the numerical analysis twice: (1) assuming a low cohesion in line with CIRIA C574 \(Lord et al., 2002\) to induce conservative estimates of ground displacements and (2) assuming a cohesion of the value of the unconfined compressive strength obtained from site investigations to induce conservative wall bending moments.
2. This work suggests that diaphragm wall shafts, with a similar joint construction technique, can be modelled with isotropic wall stiffness and that there is no need to reduce the circumferential stiffness, as proposed by previous studies.
3. For future excavations it may be possible to reduce the wall thickness as this has a minor influence on structural forces and movements, provided this complies with the requirements on reinforcement design imposed by Eurocode 2 \(British Standards Institution, 1992\).
4. Empirical formulas, such as New and Bowers \(1994\), cannot be transferred to excavations under different conditions. It is advised against the use of these empirical formulas to estimate ground movements around diaphragm shafts. Numerical predictions instead provide a more realistic picture of excavation-induced ground movements, but cannot be used to obtain movements occurring during wall installation, unless more complex three-dimensional models are used.
5. Above all, this study has shown that the ground movements around Abbey Mills shaft were very small. Future diaphragm wall shafts using a similarly strong joint construction method (cutting into the adjacent panel with a hydrofraise) may hence not need expensive large-scale instrumentation schemes, as it has been confirmed that ground movements are minimal and risks are low. Extensive protective measures for adjacent infrastructure may thus also be reduced.

## 8.3 Recommendations for future work

A three-dimensional numerical model would be able to simulate the diaphragm wall installation panel by panel and hence take beneficial arching effects into account. This may allow modelling of the wall installation and associated ground movements more realistically. Other construction phases, such as the dewatering trial prior to excavation or the culvert construction, may be simulated with a three-dimensional model.

While diaphragm walls with strong joints exhibit low risk, it is still advised to conduct further field studies on shafts under different conditions. Shaft sinkings for example seem to result in larger ground movements, as New and Bowers' \(1994\) work suggested, but this requires confirmation.

This is the first study to investigate diaphragm wall anisotropy. Further case studies may need to be conducted to validate the findings of this thesis and to investigate whether the joint construction technique plays a role.

FO instrumentation needs to become more robust so that less breakages occur when deployed on site. Further studies could investigate the use of different FO cables and their suitability for strain sensing applications. FO sensing has to move towards automatic monitoring where the read-out unit can remain on site and data is processed with automated software to immediately alert of excessive or unexpected movements.

# References

- Allenby, D., Waley, G., and Kilburn, D. (2009). Examples of open caisson sinking in Scotland. *Proceedings of the ICE - Geotechnical Engineering*, 162(1):59–70.
- Anagnostopoulos, C. and Georgiadis, K. (2001). Behaviour of an instrumented circular diaphragm wall. In: Anagnostopoulos, A., Pachakis, M., and Tsatsanifos, C. (eds.), *Proceedings of the 15th International Conference on Soil Mechanics and Geotechnical Engineering*, pages 1061–1064. Balkema, Rotterdam.
- Ariizumi, K., Kumagai, T., and Kashiwagi, A. (2000). Behavior of large-scale cylindrical earth retaining wall. In: Kusakabe, O., Fujita, K., and Miyazaki, Y. (eds.), *Proceedings of the International Symposium on Geotechnical Aspects of Underground Construction in Soft Ground*, pages 481–486. Balkema, Rotterdam.
- Bell, F. G. (1977). A note on the physical properties of the Chalk. *Engineering Geology*, 11(1977):217–225.
- Berezantzev, V. G. (1958). Earth pressure on the cylindrical retaining wall. In: *Proceedings Conference on Earth Pressure Problems*, volume 2, pages 21–27. Brussels.
- Bilfinger Spezialtiefbau GmbH (2013). *Diaphragm walls, cut-off walls and slurry walls*. [online] Available at: [http://www.spezialtiefbau.bilfinger.](http://www.spezialtiefbau.bilfinger.com/fileadmin/con-spezialtiefbau/verfahren/en/Diaphragm_walls_Cut-off_walls_and_slurry_walls.pdf) [com/fileadmin/con-spezialtiefbau/verfahren/en/Diaphragm\\_walls\\_Cut-off\\_](http://www.spezialtiefbau.bilfinger.com/fileadmin/con-spezialtiefbau/verfahren/en/Diaphragm_walls_Cut-off_walls_and_slurry_walls.pdf) [walls\\_and\\_slurry\\_walls.pdf](http://www.spezialtiefbau.bilfinger.com/fileadmin/con-spezialtiefbau/verfahren/en/Diaphragm_walls_Cut-off_walls_and_slurry_walls.pdf), [Accessed 27 Oct 2013].
- Bolton, M. D., Lam, S. Y., and Vardanega, P. J. (2010). Predicting and Controlling Ground Movements around Deep Excavations. In: *11th International Conference on Geotechnical Challenges in Urban Regeneration*. DFI-EFFC, London.
- Brinkgreve, R. B. J., Broere, W., and Waterman, D. (2009). *PLAXIS 2D Reference Manual Version 9.0*. PLAXIS, Delft.
- British Standards Institution (1992). *BS EN 1992-1-1:2004 Eurocode 2: Design of concrete structures - Part 1-1: General rules and rules for buildings*. BSI, London.
- British Standards Institution (2004a). *BS EN 1997-1:2004 Eurocode 7: Geotechnical Design - Part 1: General rules*. BSI, London.
- British Standards Institution (2004b). *NA to BS EN 1997-1:2004 UK National Annex to Eurocode 7: Geotechnical design – Part 1: General rules*. BSI, London.

- Burland, J. B. (1989). Ninth Laurits Bjerrum Memorial Lecture: "Small is beautiful"—the stiffness of soils at small strains. *Canadian Geotechnical Journal*, 26:449–516.
- Burland, J. B. and Hancock, R. J. R. (1977). Underground car park at the House of Commons, London: Geotechnical aspects. *The Structural Engineer*, 55(2):87– 100.
- Cabarkapa, Z., Milligan, G. W. E., Menkiti, C. O., Murphy, J., and Potts, D. M. (2003). Design and performance of a large diameter shaft in Dublin boulder Clay. In: Newson, T. A. (ed.), *Proceedings of the BGA International Conference on Foundations*, pages 175–185. Thomas Telford Ltd., London.
- Chandrasegaran, S., Gilbert, C., Jeanmaire, T., Nasim, S., Quereshi, J., Lauw, S. W., Tan, S. A., Harry, Perez, F., Calimag, F., and Furio, R. (2006). Triple Cellular Diaphragm Wall in Singapore Marine Clay. In: *Proceedings of the International Conference on Deep Excavations*. Singapore, 28-30 Jun 2006.
- Cheng, Y. M. and Hu, Y. Y. (2005). Active earth pressure on circular shaft lining obtained by simplified slip line solution with general tangential stress coefficient. *Yantu Gongcheng Xuebao/ Chinese Journal of Geotechnical Engineering*, 27(1):110–115.
- Cheng, Y. M., Hu, Y. Y., and Wei, W. B. (2007). General Axisymmetric Active Earth Pressure by Method of Characteristics - Theory and Numerical Formulation. *International Journal of Geomechanics*, 7(1):1–15.
- Chun, B. and Shin, Y. (2006). Active earth pressure acting on the cylindrical retaining wall of a shaft. *South Korea Ground Environmental Engineering Journal*, 7(4):15–24.
- Clayton, C. (1990). The mechanical properties of the Chalk. In: *Chalk: Proceedings of the International Chalk Symposium*, pages 213–232. Thomas Telford Ltd., London.
- Conti, R., Sanctis, L., and Viggiani, G. M. B. (2012). Numerical modelling of installation effects for diaphragm walls in sand. *Acta Geotechnica*, 7(3):219–237.
- Coulomb, C. A. (1776). Essai sur une application des regles des maximis et minimis a quelques problems de statique relatifs a l'architecture. In: *Memoires de Mathématique et de Physique, Présentés a l'Académie Royale des sciences, par divers Savants, et lûs dans ses Assemblées, Paris*, pages 343–382.
- De Moor, E. K. (1994). An analysis of bored pile/diaphragm wall installation effects. *Géotechnique*, 44(2):341–347.
- Dunnicliff, J. (1988). *Geotechnical Instrumentation for Monitoring Field Performance*. John Wiley & Sons, New York.

- Enami, A., Morishita, H., Ogihara, M., Homma, M., H., T., and Hiramatsu, Y. (1996). Earth pressure acting on a deep circular shaft wall. In: Mair, R. J. and Taylor, R. N. (eds.), *Proceedings of the International Symposium on Geotechnical Aspects of Underground Construction in Soft Ground*, pages 117–122. Balkema, Rotterdam.
- Fuchsberger, M. (1975). Some practical aspects of diaphragm wall construction. In: Darwent, T. (ed.), *Proceedings of the Conference on Diaphragm Walls & Anchorages*, pages 75–79. Thomas Telford Ltd., London.
- Fujii, T., Hagiwara, T., Ueno, K., and Taguchi, A. (1994). Experiment and analysis of earth pressure on an axisymmetric shaft in sand. In: Leung, C.F.Lee, F. and Tan, T. (eds.), *Proceedings of the International Conference Centrifuge 94*, pages 791–796. Balkema, Rotterdam.
- Fujikura (2009). *Specification for singlemode optical fibre sensor cable (JBT-03813)*, Data sheet. Fujikura Ltd., Tokyo.
- Gaba, A., Simpson, B., Powrie, W., and Beadman, D. (2003). *CIRIA C580 Embedded retaining walls - guidance for economic design*. CIRIA, London.
- Gasparre, A. (2005). *Advanced Laboratory Characterisation of London Clay*. PhD thesis, Imperial College London.
- Geocentrix (2011). *Geocentric RWaRD 2.7 Reference Manual - Embedded retaining wall design*. Geocentrix Ltd., Surry.
- Geotechnical Consulting Group (2007). *1D0101-G0G00-01004 Crossrail Settlement Estimation Procedure: Box Excavations & Shafts*, Technical report. Crossrail, London.
- Gerolymos, N., Anastasopoulos, I., and Gazetas, G. (2007). Opening ceremony shaft for the Athens 2004 Olympic Games. *Proceedings of the ICE - Geotechnical Engineering*, 160(2):61–71.
- Gesolve (2002). *WALLAP - Retaining Wall Analysis Program*. [online] Available at: <http://www.geosolve.co.uk/wallap1.htm>, [Accessed 30 Oct 2013].
- Goto, S. and Iguro, M. (1989). The world's first high-strength, super-deep slurry wall. In: *Proceedings of the 12th International Conference on Soil Mechanics and Foundation Engineering*, pages 1487–1490. Balkema, Rotterdam.
- Gourvenec, S. M. and Powrie, W. (1999). Three-dimensional finite-element analysis of diaphragm wall installation. *Géotechnique*, 49(6):801–823.
- Gunn, M. J. and Clayton, C. R. I. (1992). Installation effects and their importance in the design of earth-retaining structures. *Géotechnique*, 42(1):137–141.

- Hagiwara, T., Imamura, S., Fujii, T., Nomoto, T., and Kusakabe, O. (1998). Earth pressure acting on a deep circular shaft and associated ground deformation. In: Kusakabe, O. and Takemura, J. (eds.), *Proceedings of the International Conference Centrifuge 98*, pages 643–648. Balkema, Rotterdam.
- Herten, M. and Pulsfort, M. (1999). Determination of spatial earth pressure on circular shaft constructions. *Granular Matter*, 2(1):1–7.
- Hight, D., Ellison, R., and Page, D. (2004). *CIRIA C583 Engineering in the Lambeth Group*. CIRIA, London.
- Hight, D. W., Gasparre, A., Nishimura, S., Minh, N. A., Jardine, R. J., and Coop, M. R. (2007). Characteristics of the London Clay from the terminal 5 site at heathrow airport. *Géotechnique*, 57(1):3–18.
- Hoek, E., Carranza-Torres, C., and Corkum, B. (2002). Hoek-Brown criterion – 2002 edition. In: Bawden, H., Curran, J., and Telsenicki, M. (eds.), *Proceedings of the 5th North American rock mechanics symposium (NARMS-TAC 2002)*, pages 267–273. Mining Innovation and Technology, Toronto.
- Hoek, E., Marinos, P., and Benissi, M. (1998). Applicability of the Geological Strength Index (GSI) classification for very weak and sheared rock masses. The case of the Athens Schist Formation. *Bulletin of Engineering Geology and the Environment*, 57(2):151–160.
- Itasca (2008). *FLAC Version 6.0 Fast Lagrangian Analysis of Continua, Theory and Background*, User manual. Itasca Consulting Group Inc., Minneapolis, Minnesota.
- Itasca (2011a). *FLAC Version 7.0 Fast Lagrangian Analysis of Continua, FISH in FLAC*, User manual. Itasca Consulting Group Inc., Minneapolis, Minnesota.
- Itasca (2011b). *FLAC Version 7.0 Fast Lagrangian Analysis of Continua, Fluid-Mechanical Interactions*, User manual. Itasca Consulting Group Inc., Minneapolis, Minnesota.
- Iten, M. (2011). *Novel Applications of Distributed Fiber-Optic Sensing in Geotechnical Engineering*. PhD thesis, ETH Zurich.
- Jardine, R. J., Potts, D. M., Fourie, A. B., and Burland, J. B. (1986). Studies of the influence of non-linear stress–strain characteristics in soil–structure interaction. *Géotechnique*, 36(3):377–396.
- Kim, K.-Y., Lee, D.-S., Cho, J., Jeong, S.-S., and Lee, S. (2013). The effect of arching pressure on a vertical circular shaft. *Tunnelling and Underground Space Technology*, 37:10–21.
- Kung, G. T. C., Hsiao, E. C. L., and Juang, C. H. (2007). Evaluation of a simplified small-strain soil model for analysis of excavation-induced movements. *Canadian Geotechnical Journal*, 44(6):726–736.

- Kung, T. C. (2003). *Surface Settlement Induced by Excavation with Consideration of Small-Strain Behaviour of Taipei Silty Clay*. PhD thesis, National Taiwan University of Science and Technology.
- Kung, T. C. and Ou, C. Y. (2006). Prediction of surface settlement caused by excavation. In: Bakker, K. J., Broere, W., and Bezuijen, A. (eds.), *Proceedings of the 5th International Symposium TC28 on Geotechnical Aspects of Underground Construction in Soft Ground*, pages 853–858. Taylor & Francis Group/Balkema, Leiden.
- Kusakabe, O. (1982). *Stability of excavations in soft clay*. PhD thesis, University of Cambridge.
- Lade, P. V., Jessberger, H. L., Makowski, E., and Jordan, P. (1981). Modeling of Deep Shafts in Centrifuge Tests. In: *Proceedings of the 10th International Conference on Soil Mechanics and Foundation Engineering*, pages 683–691. Balkema, Rotterdam.
- Lam, S. Y. (2010). *Ground Movements due to Excavation in Clay Physical and Analytical Models*. PhD thesis, University of Cambridge.
- Laver, R. (2010). *Long-term behaviour of twin tunnels in London Clay*. PhD thesis, University of Cambridge.
- Leica Geosystems AG (2013a). *Specifications Leica DNA digital levels*, Data sheet. [online] Available at: [http://www.leica-geosystems.co.uk/downloads123/zz/](http://www.leica-geosystems.co.uk/downloads123/zz/levels/dna/brochures/DNA_Brochure_en.pdf) [levels/dna/brochures/DNA\\_Brochure\\_en.pdf](http://www.leica-geosystems.co.uk/downloads123/zz/levels/dna/brochures/DNA_Brochure_en.pdf), [Accessed 15 Jan 2014].
- Leica Geosystems AG (2013b). *Specifications Leica TPS1200+ Series*, Data sheet. [online] Available at: [http://www.leica-geosystems.co.uk/downloads123/zz/](http://www.leica-geosystems.co.uk/downloads123/zz/tps/tps1200/brochures/Leica_TPS1200+_brochure_en.pdf) [tps/tps1200/brochures/Leica\\_TPS1200+\\_brochure\\_en.pdf](http://www.leica-geosystems.co.uk/downloads123/zz/tps/tps1200/brochures/Leica_TPS1200+_brochure_en.pdf), [Accessed 15 Jan 2014].
- Lings, M. L., Ng, C. W. W., and Nash, D. F. T. (1994). The Lateral Pressure of Wet Concrete in Diaphragm Wall Panels Cast Under Bentonite. *Proceedings of the ICE - Geotechnical Engineering*, 107(3):163–172.
- Liu, F. Q. and Wang, J. H. (2008). A generalized slip line solution to the active earth pressure on circular retaining walls. *Computers and Geotechnics*, 35(2):155– 164.
- Long, M. (2001). Database for retaining wall and ground movements due to deep excavations. *Journal of Geotechnical and Geoenvironmental Engineering*, 127(3):203–224.
- Lord, J., Clayton, C., and Mortimore, R. (2002). *CIRIA C574 Engineering in chalk*. CIRIA, London.

- Marten, S. and Bourgeois, E. (2005). Three-dimensional behaviour of a circular excavation in Nantes, France. In: Bakker, K. J., Bezuijen, A., and Broere, W. (eds.), *Geotechnical Aspects of Underground Construction in Soft Ground*, pages 867–872. Balkema, Rotterdam.
- Matthews, M. C. and Clayton, C. (2004). Large diameter plate tests on weathered in-situ Chalk. *Quarterly Journal of Engineering Geology and Hydrogeology*, 37(1):61–72.
- Mayflex Holidings Ltd. (2012). *Specifications Excel Loose Tube Internal / External Grade Fibre*, Data sheet. [online] Available at: [http://excel-networking.pl/downloads/01-specification\\_sheets/02\\_fibre/](http://excel-networking.pl/downloads/01-specification_sheets/02_fibre/02-singlemode_cable/E0094-Exc-Fibre-LT-SM-OS2.pdf) [02-singlemode\\_cable/E0094-Exc-Fibre-LT-SM-OS2.pdf](http://excel-networking.pl/downloads/01-specification_sheets/02_fibre/02-singlemode_cable/E0094-Exc-Fibre-LT-SM-OS2.pdf), [Accessed 26 Apr 2013].
- McNamara, A. M., Roberts, T. O. L., Morrison, P. R. J., and Holmes, G. (2008). Construction of a deep shaft for Crossrail. *Proceedings of the ICE - Geotechnical Engineering*, 161(6):299–309.
- Mikkelsen, P. E. (2003). Advances in Inclinometer Data Analysis. In: Myrvoll, F. (ed.), *6th International Symposium on Field Measurements in Geomechanics (FMGM 2003)*. Swets & Zeitlinger B.V., Lisse.
- Mohamad, H. (2008). *Distributed Optical Fibre Strain Sensing of Geotechnical Structures*. PhD thesis, University of Cambridge.
- Mohamad, H., Soga, K., Pellew, A., and Bennett, P. J. (2011). Performance Monitoring of a Secant-Piled Wall Using Distributed Fiber Optic Strain Sensing. *Journal of Geotechnical and Geoenvironmental Engineering*, 137(12):1236–1243.
- Morgan Sindall (2012). *UPS-GTC-XX-XXX-RPT-26959-R03 Geotechnical Interpretative Report (GIR) Part 1: Geotechnical Interpretation*, Technical report. Morgan Sindall.
- Morrison, P. R. J., McNamara, A. M., and Roberts, T. O. L. (2004). Design and construction of a deep shaft for Crossrail. *Proceedings of the ICE - Geotechnical Engineering*, 157(4):173–182.
- Mott MacDonald (2012). *MMD-ENV-XX-XXX-RPT-73965-A01 Construction Groundwater Monitoring Eastern Tunnel Alignment Round 24 and Abbey Mills Round 13 Summary Report*, Technical report. Mott MacDonald.
- Muramatsu, M. and Abe, Y. (1996). Considerations in shaft excavation and peripheral ground deformation. In: Mair, R. J. and Taylor, R. N. (eds.), *Geotechnical Aspects of Underground Construction in Soft Ground*, pages 173–178. Balkema, Rotterdam.

- New, B. M. and Bowers, K. H. (1994). Ground movement model validation at the Heathrow Express trial tunnel. In: *Proceedings of the 7th International Symposium, Tunnelling '94*, pages 301–329. Institution of Mining and Metallurgy, London.
- Newman, T. and Wong, H.-Y. (2011). Sinking a jacked caisson within the London Basin geological sequence for the Thames Water Ring Main extension. *Quarterly Journal of Engineering Geology and Hydrogeology*, 44(2):221–231.
- Ng, C. W. W. and Yan, R. W. M. (1999). Three-dimensional modelling of a diaphragm wall construction sequence. *Géotechnique*, 49(6):825–834.
- Oasys Ltd. (2007). *Oasys Stawal Version 18.2*, User manual. Oasys Ltd., Newcastle-Upon-Tyne.
- Oasys Ltd. (2010). *Oasys Frew Version 19.0*, User manual. Oasys Ltd., Newcastle-Upon-Tyne.
- Ohno, H., Naruse, H., Yasue, N., Miyajima, Y., Uchiyama, H., Sakairi, Y., and Li, Z. X. (2001). Development of highly stable BOTDR strain sensor employing microwave heterodyne detection and tunable electric oscillator. In: Asundi, A. K., Osten, W., and Varadan, V. K. (eds.), *Proceedings of Advanced Photonic Sensors and Applications II, Proceedings of SPIE*, volume 4596, pages 74–85. SPIE.
- Omnisens SA (2012). *DITEST-STA-R*, Data sheet. Omnisens SA, Morges. [online] Available at: <http://www.omnisens.ch/ditest/3521-ditest-sta-r.php>, [Accessed 26 Apr 2013].
- Osman, A. S. and Bolton, M. D. (2006). Ground movement predictions for braced excavations in undrained clay. *Journal of Geotechnical and Geoenvironmental Engineering*, 132(4):465–477.
- Otta, J. (2012). *CH2MHILL | Acess Water | Final Preparation Underway for Start of Tunneling in London*. [online] Available at: [http://www.ch2mhillblogs.com/](http://www.ch2mhillblogs.com/water/2012/02/06/tunneling-in-london-lee-tunnel/) [water/2012/02/06/tunneling-in-london-lee-tunnel/](http://www.ch2mhillblogs.com/water/2012/02/06/tunneling-in-london-lee-tunnel/), [Accessed 27 Oct 2013].
- Pairaudeau, H. (2011). *Construction and Performance of Shafts*. MEng thesis, University of Cambridge.
- Parashar, S., Mitchell, R., Hee, M., Sanmuganathan, D., and Nicholson, G. (2007). Performance Monitoring of Deep Shafts at Changi WRP Project, Singapore. In: DiMaggio, J. and Osborn, P. (eds.), *Proceedings of the 7th International Symposium on Field Measurements in Geomechanics (FMGM 2007)*. American Society of Civil Engineers (ASCE), Reston, VA.
- Peck, R. B. (1969). Advantages and limitations of the observational method in applied soil mechanics. *Géotechnique*, 19(2):171–187.

- Placzek, D. and Londong, D. (1994). Tragverhalten eines großen, kreisrunden, horizontal nicht gestützten Schlitzwandschachtes. In: *Verträge der Baugrundtagung 1994 in Köln*, pages 295–308. Deutsche Gesellschaft für Geotechnik e.V., Essen.
- Potts, D. M. and Zdravkovic, L. (1999). *Finite element analysis in geotechnical engineering: Theory*. Thomas Telford, London.
- Powderham, A. J. (2000). Design and construction of a deep circular cofferdam in collapsed ground. In: *Geotechnical Aspects of Underground Construction in Soft Ground*, pages 527–532. Balkema, Rotterdam.
- Powderham, A. J. (2002). The observational method - Learning from projects. *Proceedings of the ICE - Geotechnical Engineering*, 155(1):59–69.
- Powrie, W. and Bolton, M. D. (1988). Behaviour of diaphragm walls in clay prior to collapse. *Géotechnique*, 38(2):167–189.
- Powrie, W., Pantelidou, H., and Stallebrass, S. E. (1998). Soil stiffness in stress paths relevant to diaphragm walls in clay. *Géotechnique*, 48(4):483–494.
- Prater, E. G. (1977). Examination of some theories of earth pressure on shaft linings. *Canadian Geotechnical Journal*, 14(1):91–106.
- Puller, M. (2003). *Deep Excavations: a practical manual*. Thomas Telford, London, 2nd edition.
- Pyke, R. (1979). Non-linear soil models for irregular cyclic loadings. *Journal of the Geotechnical Engineering Division*, 105(6):715–726.
- Rankin, W. and May, R. (1996). Geotechnical Properties. In: Harris, C., Hart, M., Varley, P., and Warren, C. (eds.), *Engineering Geology of the Channel Tunnel*. Thomas Telford, London.
- Richards, D. J., Clark, J., and Powrie, W. (2006). Installation effects of a bored pile wall in overconsolidated clay. *Géotechnique*, 56(6):411–425.
- Schwamb, T., Elshafie, M., Ouyang, Y., Fuentes, R., Janmonta, K., Soga, K., Ferreira, P., and Swain, A. (2011). Monitoring of a secant piled wall using fibre optics sensors. In: Gattermann, J. (ed.), *8th International Symposium on Field Measurements in GeoMechanics (FMGM2011)*. Berlin, 12-16 Sep 2011.
- Sideri, M. (2012). *A Study of Ground Loading on Shafts*. MSc thesis, Imperial College London.
- Simpson, B. and Powrie, W. (2001). Embedded retaining walls: theory, practice and understanding. In: Anagnostopoulos, A., Pachakis, M., and Tsatsanifos, C. (eds.), *Proceedings of the 15th International Conference on Soil Mechanics and Geotechnical Engineering*, pages pp. 2505–2524. Balkema, Rotterdam.

- Slope Indicator (2002). *Spiral Sensor 50900199*, User manual. Slope Indicator, Kent.
- Slope Indicator (2009). *Data Reduction & Error Correction for Inclinometers*, Course training material. Slope Indicator, Kent.
- Slope Indicator (2011a). *Digitilt Inclinometer Probe*, Data sheet. Slope Indicator, Kent.
- Slope Indicator (2011b). *Digitilt Inclinometer Probe 50302599*, User manual. Slope Indicator, Kent.
- Soga, K. and O'Sullivan, C. (2010). Modeling of geomaterials behavior. *Soils and Foundations*, 50(6):861–875.
- Symons, I. and Carder, D. (1993). Stress changes in stiff clay caused by the installation of embedded retaining walls. In: Clayton, C. (ed.), *Retaining structures*, pages 227–236. Thomas Telford Ltd., London.
- Tan, Y. and Wang, D. (2013). Structural Behaviors of Large-Sized Underground Earth Retaining Systems in Shanghai. I: Unpropped Circular Diaphragm Wall. *Journal of Performance of Constructed Facilities*, \*\*:posted ahead of print 14 Oct 2013.
- Terzaghi, K. (1920). Old earth-pressure theories and new test results. *Engineering News-Record*, 85(13):632–637.
- Terzaghi, K. (1943). *Theoretical Soil Mechanics*. John Wiley & Sons, New York.
- Thames Water Utilities Limited (2013). *Thames Tideway Strategic Study*. [online] Available at: [http://infrastructure.planningportal.gov.uk/wp-content/](http://infrastructure.planningportal.gov.uk/wp-content/ipc/uploads/projects/WW010001/2. Post-Submission/Application Documents/Other Documents/8.1.1_Thames_Tideway_Strategic_Study_Executive_Summary.pdf) [ipc/uploads/projects/WW010001/2.Post-Submission/ApplicationDocuments/](http://infrastructure.planningportal.gov.uk/wp-content/ipc/uploads/projects/WW010001/2. Post-Submission/Application Documents/Other Documents/8.1.1_Thames_Tideway_Strategic_Study_Executive_Summary.pdf) [OtherDocuments/8.1.1\\_Thames\\_Tideway\\_Strategic\\_Study\\_Executive\\_Summary.](http://infrastructure.planningportal.gov.uk/wp-content/ipc/uploads/projects/WW010001/2. Post-Submission/Application Documents/Other Documents/8.1.1_Thames_Tideway_Strategic_Study_Executive_Summary.pdf) [pdf](http://infrastructure.planningportal.gov.uk/wp-content/ipc/uploads/projects/WW010001/2. Post-Submission/Application Documents/Other Documents/8.1.1_Thames_Tideway_Strategic_Study_Executive_Summary.pdf), [Accessed 20 Jan 2014].
- Thames Water Utilities Limited (2014). *Thames Tideway Tunnel - The need to clean up the Thames*. [online] Available at: [http://www.thamestidewaytunnel.co.](http://www.thamestidewaytunnel.co.uk/what-we-are-doing/the-need-to-clean-up-the-thames/) [uk/what-we-are-doing/the-need-to-clean-up-the-thames/](http://www.thamestidewaytunnel.co.uk/what-we-are-doing/the-need-to-clean-up-the-thames/), [Accessed 31 Jan 2014].
- Thomas, A. (2009). *Sprayed Concrete Lined Tunnels*. Taylor & Francis, London.
- Tobar, T. and Meguid, M. A. (2010). Comparative evaluation of methods to determine the earth pressure distribution on cylindrical shafts: A review. *Tunnelling and Underground Space Technology*, 25(2):188–197.
- Tobar, T. and Meguid, M. A. (2011). Experimental Study of the Earth Pressure Distribution on Cylindrical Shafts. *Journal of Geotechnical and Geoenvironmental Engineering*, 137(11):1121–1125.

- Ueno, K. and Yokoyama, Y. (1996). Earth pressures acting on flexible circular shafts in sand. In: *Proceedings of the International Symposium TC28 on Geotechnical Aspects of Underground Construction in Soft Ground*, pages 237–242. Balkema, Rotterdam.
- Vardanega, P. J. and Bolton, M. D. (2011). Strength mobilization in clays and silts. *Canadian Geotechnical Journal*, 48(10):1485–1503.
- Ventouras, K. (2005). *Engineering Behaviour of Thanet Sand*. PhD thesis, Imperial College London.
- Vermeer, P. and de Borst, R. (1984). Non-associated plasticity for soils, concrete and rock. *HERON*, 29(3).
- Virollet, B., Gilbert, C., and Deschamps, R. (2006). Recent Advances in Large Diameter Diaphragm Wall Shafts. In: *Proceedings of the 31st Annual Conference on Deep Foundations*. Washington DC.
- Walter, J. P. and Tarallo, F. (1985). Soutènement d'une fouille par une paroi cylindrique. In: *Proceedings of the 11th International Conference on Soil Mechanics and Foundation Engineering*, pages 2141–2144. Balkema, Rotterdam.
- Watson, P. C., Warren, C. D., and Eddie, C. (1999). CTRL North Downs Tunnel. In: *Proceedings Tunnelling International Symposium*, pages 301–323. Institution of Mining and Metallurgy, London.
- Westergaard, H. M. (1941). Plastic state of stress around deep well. *Civil Engineering (London)*, 36(421):527–528.
- Wong, R. C. K. and Kaiser, P. K. (1988). Behaviour of vertical shafts: Reevaluation of model test results and evaluation of field measurements. *Canadian Geotechnical Journal*, 25(2):338–352.
- Wongsaroj, J. (2005). *Three-dimensional finite element analysis of short and long-term ground response to open-face tunnelling in stiff clay*. PhD thesis, University of Cambridge.
- Yokogawa (2005). *AQ8603 Optical Fiber Strain Analyzer*, Data sheet. Yokogawa Electric Corporation, Tokyo.
- Zdravkovic, L., Potts, D. M., and St. John, H. D. (2005). Modelling of a 3D excavation in finite element analysis. *Géotechnique*, 55(7):497–513.
